#!/usr/bin/env python3
"""
Security audit script for modules using potentially dangerous functions
"""

import ast
import os
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple
from datetime import datetime
import json

# Dangerous functions and modules to check
DANGEROUS_PATTERNS = {
    'file_operations': {
        'functions': ['open', 'file', 'pathlib.Path', 'os.path'],
        'risk': 'File system access',
        'severity': 'HIGH'
    },
    'system_calls': {
        'functions': ['os.system', 'subprocess.run', 'subprocess.call', 'subprocess.Popen'],
        'risk': 'System command execution',
        'severity': 'CRITICAL'
    },
    'code_execution': {
        'functions': ['eval', 'exec', 'compile', '__import__'],
        'risk': 'Dynamic code execution',
        'severity': 'CRITICAL'
    },
    'network_operations': {
        'functions': ['socket', 'urllib', 'requests', 'httpx', 'aiohttp'],
        'risk': 'Network access',
        'severity': 'MEDIUM'
    },
    'dangerous_builtins': {
        'functions': ['globals', 'locals', 'vars', 'dir', 'getattr', 'setattr', 'delattr'],
        'risk': 'Access to internal structures',
        'severity': 'HIGH'
    }
}

class SecurityAuditor(ast.NodeVisitor):
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.issues = []
        self.imports = set()
        
    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name)
        self.generic_visit(node)
        
    def visit_ImportFrom(self, node):
        if node.module:
            self.imports.add(node.module)
        self.generic_visit(node)
        
    def visit_Call(self, node):
        # Check for dangerous function calls
        func_name = self._get_func_name(node.func)
        if func_name:
            for category, info in DANGEROUS_PATTERNS.items():
                if any(pattern in func_name for pattern in info['functions']):
                    self.issues.append({
                        'line': node.lineno,
                        'function': func_name,
                        'category': category,
                        'risk': info['risk'],
                        'severity': info['severity']
                    })
        self.generic_visit(node)
        
    def visit_Name(self, node):
        # Check for dangerous built-in usage
        if isinstance(node.ctx, ast.Load):
            for category, info in DANGEROUS_PATTERNS.items():
                if node.id in info['functions']:
                    self.issues.append({
                        'line': node.lineno,
                        'function': node.id,
                        'category': category,
                        'risk': info['risk'],
                        'severity': info['severity']
                    })
        self.generic_visit(node)
        
    def _get_func_name(self, node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            parts = []
            current = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return '.'.join(reversed(parts))
        return ''

def audit_file(filepath: Path) -> Dict:
    """Audit a single Python file for security issues"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        tree = ast.parse(content)
        auditor = SecurityAuditor(str(filepath))
        auditor.visit(tree)
        
        return {
            'file': str(filepath),
            'issues': auditor.issues,
            'imports': list(auditor.imports),
            'status': 'analyzed'
        }
    except Exception as e:
        return {
            'file': str(filepath),
            'issues': [],
            'imports': [],
            'status': f'error: {str(e)}'
        }

def find_python_files(root_dir: Path, exclude_dirs: Set[str] = None) -> List[Path]:
    """Find all Python files in directory"""
    if exclude_dirs is None:
        exclude_dirs = {'__pycache__', '.git', 'venv', 'env', '.venv', 'tests'}
    
    python_files = []
    for path in root_dir.rglob('*.py'):
        # Skip excluded directories
        if any(excluded in path.parts for excluded in exclude_dirs):
            continue
        python_files.append(path)
    
    return python_files

def generate_report(results: List[Dict]) -> Dict:
    """Generate security audit report"""
    total_files = len(results)
    files_with_issues = [r for r in results if r['issues']]
    total_issues = sum(len(r['issues']) for r in results)
    
    # Count by severity
    severity_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    category_counts = {}
    
    for result in results:
        for issue in result['issues']:
            severity_counts[issue['severity']] += 1
            category = issue['category']
            category_counts[category] = category_counts.get(category, 0) + 1
    
    # Find most dangerous files
    dangerous_files = []
    for result in files_with_issues:
        critical_count = sum(1 for i in result['issues'] if i['severity'] == 'CRITICAL')
        if critical_count > 0:
            dangerous_files.append({
                'file': result['file'],
                'critical_issues': critical_count,
                'total_issues': len(result['issues'])
            })
    
    dangerous_files.sort(key=lambda x: x['critical_issues'], reverse=True)
    
    return {
        'summary': {
            'total_files_scanned': total_files,
            'files_with_issues': len(files_with_issues),
            'total_issues': total_issues,
            'severity_breakdown': severity_counts,
            'category_breakdown': category_counts
        },
        'most_dangerous_files': dangerous_files[:10],
        'all_results': results
    }

def print_report(report: Dict):
    """Print formatted security report"""
    print("\n" + "="*70)
    print("🔒 SECURITY AUDIT REPORT")
    print("="*70)
    
    summary = report['summary']
    print(f"\n📊 Summary:")
    print(f"  Files scanned: {summary['total_files_scanned']}")
    print(f"  Files with issues: {summary['files_with_issues']}")
    print(f"  Total issues found: {summary['total_issues']}")
    
    print(f"\n🚨 Severity Breakdown:")
    for severity, count in summary['severity_breakdown'].items():
        if count > 0:
            emoji = {'CRITICAL': '🔴', 'HIGH': '🟠', 'MEDIUM': '🟡', 'LOW': '🟢'}[severity]
            print(f"  {emoji} {severity}: {count}")
    
    print(f"\n📁 Issue Categories:")
    for category, count in summary['category_breakdown'].items():
        print(f"  - {category}: {count}")
    
    if report['most_dangerous_files']:
        print(f"\n⚠️  Most Dangerous Files:")
        for file_info in report['most_dangerous_files']:
            rel_path = os.path.relpath(file_info['file'])
            print(f"  - {rel_path}")
            print(f"    Critical issues: {file_info['critical_issues']}")
            print(f"    Total issues: {file_info['total_issues']}")
    
    print("\n" + "="*70)

def save_detailed_report(report: Dict, output_file: str):
    """Save detailed report to JSON file"""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Detailed report saved to: {output_file}")

def main():
    # Determine root directory
    if len(sys.argv) > 1:
        root_dir = Path(sys.argv[1])
    else:
        root_dir = Path('/workspace/langchain_api')
    
    if not root_dir.exists():
        print(f"Error: Directory {root_dir} does not exist")
        sys.exit(1)
    
    print(f"🔍 Starting security audit of: {root_dir}")
    
    # Find all Python files
    python_files = find_python_files(root_dir)
    print(f"📁 Found {len(python_files)} Python files to analyze")
    
    # Audit each file
    results = []
    for i, filepath in enumerate(python_files, 1):
        if i % 10 == 0:
            print(f"  Progress: {i}/{len(python_files)} files...")
        result = audit_file(filepath)
        if result['issues']:
            results.append(result)
    
    # Generate report
    report = generate_report(results)
    
    # Print summary
    print_report(report)
    
    # Save detailed report
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'security_audit_{timestamp}.json'
    save_detailed_report(report, output_file)
    
    # Recommendations
    print("\n💡 Recommendations:")
    print("1. Review all CRITICAL severity issues immediately")
    print("2. Ensure file operations are properly sandboxed")
    print("3. Validate all user inputs before processing")
    print("4. Use allow-lists for command execution")
    print("5. Implement proper access controls")
    
    # Exit code based on critical issues
    if report['summary']['severity_breakdown']['CRITICAL'] > 0:
        print("\n❌ Critical security issues found!")
        sys.exit(1)
    else:
        print("\n✅ No critical issues found")
        sys.exit(0)

if __name__ == '__main__':
    main()