"""Task-owned evidence navigation and deterministic detection of repeated work."""
from __future__ import annotations

from collections import Counter
import hashlib
import json

from .redact import redact_value


STATIC_READS = frozenset({'self.inspect', 'self.search', 'self.history', 'task.recall'})
PROGRESS_ACTIONS = frozenset({'workspace.write', 'workspace.replace', 'code.run', 'skill.run',
                              'self.experiment', 'self.request_upgrade', 'memory.propose',
                              'workspace.send', 'server.fetch', 'task.schedule'})


def compact_observation(content, limit):
    """Keep JSON valid; shortening a checkpoint must not destroy its envelope."""
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)
    try:
        value = json.loads(content)
    except (ValueError, TypeError):
        if len(content) <= limit and not content.lstrip().startswith('{'):
            return content
        value = {'legacy_fragment': content, 'incomplete': True}
    if len(content) <= limit and not (isinstance(value, dict) and value.get('legacy_fragment')):
        return content

    def shrink(item, width, depth=0):
        if depth > 8:
            return '[nested data omitted]'
        if isinstance(item, str):
            return item if len(item) <= width else item[:width] + ' [truncated]'
        if isinstance(item, list):
            return [shrink(child, width, depth + 1) for child in item[:8]]
        if isinstance(item, dict):
            return {str(key)[:80]: shrink(child, width, depth + 1) for key, child in list(item.items())[:32]}
        return item

    for width in (800, 400, 160, 64):
        result = shrink(value, width)
        if isinstance(result, dict):
            result['context_summary'] = {'original_characters': len(content), 'full_evidence': 'task.recall'}
        text = json.dumps(result, ensure_ascii=False)
        if len(text) <= limit:
            return text
    return json.dumps({'ok': value.get('ok') if isinstance(value, dict) else None,
                       'context_summary': True, 'full_evidence': 'task.recall',
                       'preview': content[:max(0, limit // 2)]}, ensure_ascii=False)


class WorkContext:
    def __init__(self, queue):
        self.queue = queue

    @staticmethod
    def _canonical_content(identifier, row, event):
        if not event or event['role'] != 'tool' or event['session'] != 'work:' + identifier or len(event['content']) > 300000:
            return None
        try:
            meta, value = json.loads(event['meta']), json.loads(event['content'])
            if not (meta.get('job') == identifier and meta.get('tool') == row['name'] and
                    isinstance(value, dict) and type(value.get('ok')) is bool):
                return None
            saved = json.loads(row['outcome'])
            raw = json.dumps(redact_value(value), ensure_ascii=False, allow_nan=False).encode()
            verified_summary = (isinstance(saved, dict) and saved.get('truncated') is True and
                                saved.get('sha256') == hashlib.sha256(raw).hexdigest())
            return event['content'] if saved == value or verified_summary else None
        except (ValueError, TypeError, AttributeError):
            return None

    def _rows(self, identifier):
        with self.queue.connection() as db:
            db.execute('BEGIN')
            rows = db.execute('SELECT number,name,arguments,outcome,event_id FROM task_steps '
                              'WHERE job_id=? ORDER BY number DESC LIMIT 512', (identifier,)).fetchall()
            events_available = db.execute("SELECT 1 FROM sqlite_master WHERE name='events'").fetchone() is not None
            result = []
            for row in reversed(rows):
                outcome = json.loads(row['outcome'])
                if outcome.get('truncated') is True and row['event_id'] and events_available:
                    event = db.execute('SELECT role,session,meta,content FROM events WHERE id=?', (row['event_id'],)).fetchone()
                    original = self._canonical_content(identifier, row, event)
                    if original is not None:
                        outcome = json.loads(original)
                result.append({**dict(row), 'arguments': json.loads(row['arguments']), 'outcome': outcome})
        return result

    def summary(self, identifier):
        rows = self._rows(identifier)
        reads, failures = Counter(), Counter()
        repeat_count = static_count = no_new_reads = 0
        files = {}
        recent = []
        last_read_count = last_failure_count = 0
        for row in rows:
            name, args, outcome = row['name'], row['arguments'], row['outcome']
            result = outcome.get('result', {})
            ok = outcome.get('ok') is True
            failed_execution = (ok and name in {'code.run', 'skill.run'} and isinstance(result, dict) and
                                (result.get('exit_code') != 0 or result.get('timed_out') or result.get('error')))
            failed_experiment = (ok and name == 'self.experiment' and isinstance(result, dict) and
                                 result.get('status') not in {'regression_passed', 'improved_on_provided_case'})
            if ok and name in PROGRESS_ACTIONS and not failed_execution and not failed_experiment:
                reads.clear(); failures.clear()
                repeat_count = static_count = no_new_reads = 0
                last_read_count = last_failure_count = 0
            fingerprint = hashlib.sha256(json.dumps([name, args, outcome], sort_keys=True,
                                                   ensure_ascii=False).encode()).hexdigest()
            if outcome.get('ok') is False or failed_execution or failed_experiment:
                # Durations and freshly generated experiment IDs are not new evidence.
                failure = {'error': outcome.get('error'), 'kind': outcome.get('error_kind')}
                if isinstance(result, dict):
                    failure.update({k: result.get(k) for k in ('exit_code', 'timed_out', 'error', 'status', 'reason', 'input_manifest')})
                failure_key = hashlib.sha256(json.dumps([name, args, failure], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                failures[failure_key] += 1
                last_failure_count = failures[failure_key]
                last_read_count = 0
            elif name in STATIC_READS:
                static_count += 1
                reads[fingerprint] += 1
                last_read_count = reads[fingerprint]
                last_failure_count = 0
                if reads[fingerprint] > 1:
                    repeat_count += 1
                    no_new_reads += 1
                else:
                    no_new_reads = 0
            elif name not in {'task.plan', 'task.criteria', 'task.progress', 'task.list'}:
                last_read_count = last_failure_count = 0
            if name == 'self.inspect' and ok and isinstance(result, dict) and result.get('path'):
                key = (str(result['path'])[:200], str(result.get('sha256', ''))[:64])
                entry = files.setdefault(key, {'path': key[0], 'sha256': key[1], 'reads': 0,
                                               'last_step': row['number'], 'pages': []})
                entry['reads'] += 1
                entry['last_step'] = row['number']
                page = {k: result[k] for k in ('start_line', 'end_line', 'offset', 'next_offset') if k in result}
                page['step'] = row['number']
                # Each page links to its own durable observation, including old pages.
                previous_page = next((p for p in entry['pages'] if {k:v for k,v in p.items() if k != 'step'} ==
                                      {k:v for k,v in page.items() if k != 'step'}), None)
                if previous_page is not None:
                    previous_page['step'] = row['number']
                else:
                    entry['pages'].append(page)
                entry['pages'] = entry['pages'][-6:]
            recent.append({'step': row['number'], 'tool': name, 'ok': outcome.get('ok'), 'event_id': row['event_id']})
        maximum = max(reads.values(), default=0)
        maximum_failure = max(failures.values(), default=0)
        blocked = last_read_count >= 5 or last_failure_count >= 4 or (repeat_count >= 10 and no_new_reads >= 6)
        warning = maximum >= 3 or maximum_failure >= 2 or repeat_count >= 5
        return redact_value({'inspected_files': sorted(files.values(), key=lambda x: x['last_step'])[-16:],
                'recent_steps': recent[-16:], 'retained_step_window': len(rows),
                'recall': 'task.recall(number, offset) reads the original observation of this task only',
                'loop_guard': {'status': 'blocked' if blocked else 'warning' if warning else 'clear',
                               'same_read_count': maximum, 'same_failure_count': maximum_failure,
                               'repeated_reads_since_action': repeat_count, 'static_reads_since_action': static_count,
                               'guidance': ('Repeated unchanged reads are not progress. Use known evidence and self.search; '
                                            'make a bounded experiment or explain the exact unavailable capability. '
                                            'task.plan and narration do not reset this detector.') if warning else ''}})

    def recall(self, identifier, number, *, offset=0, limit=12000):
        if (type(number) is not int or not 1 <= number <= 100000 or type(offset) is not int or
                offset < 0 or type(limit) is not int or not 1 <= limit <= 12000):
            raise ValueError('Use a positive step number, nonnegative offset and limit 1-12000')
        with self.queue.connection() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT name,outcome,event_id FROM task_steps WHERE job_id=? AND number=?',
                             (identifier, number)).fetchone()
            if row is None:
                raise ValueError('No observation for this step in the current task')
            content = row['outcome']
            canonical = False
            if row['event_id'] and db.execute("SELECT 1 FROM sqlite_master WHERE name='events'").fetchone():
                event = db.execute('SELECT role,session,meta,content FROM events WHERE id=?', (row['event_id'],)).fetchone()
                original = self._canonical_content(identifier, row, event)
                if original is not None:
                    content, canonical = original, True
        # Old imports may predate redaction. Page only the sanitized representation.
        value = redact_value(json.loads(content))
        text = json.dumps(value, ensure_ascii=False)
        if len(text) > 300000:
            raise ValueError('Observation exceeds recall bound')
        begin = min(offset, len(text)); end = min(begin + limit, len(text))
        return {'number': number, 'tool': row['name'], 'event_id': row['event_id'], 'canonical_event': canonical,
                'content': text[begin:end], 'format': 'JSON text; concatenate pages before parsing',
                'offset': begin, 'next_offset': end if end < len(text) else None, 'total_chars': len(text),
                'sha256': hashlib.sha256(text.encode()).hexdigest(), 'read_only': True}
