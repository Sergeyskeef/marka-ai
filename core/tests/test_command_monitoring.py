import pytest
from langchain_api.core.command_monitoring import CommandMonitoringSystem, CommandEvent
import os

def test_log_command_and_result(tmp_path):
    cms = CommandMonitoringSystem()
    # Логируем команду
    event = cms.log_command(
        command="test_command",
        source="test_source",
        user_id="user123",
        parameters={"param1": 1},
        metadata={"meta": "data"}
    )
    assert isinstance(event, CommandEvent)
    assert event.command == "test_command"
    assert event.source == "test_source"
    assert event.user_id == "user123"
    # Логируем результат
    cms.log_result(event, result="ok", success=True, execution_time=0.5)
    assert event.result == "ok"
    assert event.success is True
    assert event.execution_time == 0.5


def test_analyze_command_patterns():
    cms = CommandMonitoringSystem()
    for i in range(5):
        event = cms.log_command(
            command=f"cmd_{i%2}",
            source="test",
            user_id=f"user{i%2}"
        )
        cms.log_result(event, result="done", success=(i%2==0), execution_time=0.1*i)
    analysis = cms.analyze_command_patterns()
    assert analysis['total_commands'] == 5
    assert 'cmd_0' in analysis['most_common_commands']
    assert 'cmd_1' in analysis['most_common_commands']
    assert analysis['success_rate'] < 1.0
    assert analysis['average_execution_time'] > 0


def test_export_and_clear_history(tmp_path):
    cms = CommandMonitoringSystem()
    event = cms.log_command(command="cmd", source="test")
    cms.log_result(event, result="ok")
    export_path = tmp_path / "export.json"
    assert cms.export_history(str(export_path)) is True
    assert os.path.exists(export_path)
    cms.clear_history()
    assert len(cms.command_history) == 0 