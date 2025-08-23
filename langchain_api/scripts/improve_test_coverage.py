#!/usr/bin/env python3
"""
Script to analyze and improve test coverage
"""

import subprocess
import sys
import os
from pathlib import Path
import json
import re

def run_coverage_report():
    """Run pytest with coverage and generate report"""
    print("🧪 Running tests with coverage...")
    
    cmd = [
        "python", "-m", "pytest",
        "tests/",
        "--cov=app",
        "--cov=core",
        "--cov-report=term-missing",
        "--cov-report=json",
        "-v"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd="/workspace/langchain_api")
        print(result.stdout)
        if result.stderr:
            print("Errors:", result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"Error running tests: {e}")
        return False

def analyze_coverage():
    """Analyze coverage report and find files with low coverage"""
    coverage_file = Path("/workspace/langchain_api/coverage.json")
    
    if not coverage_file.exists():
        print("❌ Coverage report not found. Run tests first.")
        return []
    
    with open(coverage_file) as f:
        data = json.load(f)
    
    files_info = []
    for file_path, file_data in data['files'].items():
        coverage_percent = file_data['summary']['percent_covered']
        missing_lines = file_data['missing_lines']
        
        if coverage_percent < 80:  # Target 80% coverage
            files_info.append({
                'path': file_path,
                'coverage': coverage_percent,
                'missing_lines': len(missing_lines),
                'missing': missing_lines[:10]  # First 10 missing lines
            })
    
    # Sort by coverage (lowest first)
    files_info.sort(key=lambda x: x['coverage'])
    
    return files_info

def generate_test_template(module_path: str) -> str:
    """Generate test template for a module"""
    module_name = Path(module_path).stem
    test_name = f"test_{module_name}"
    
    template = f'''"""
Tests for {module_name}
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import asyncio

# Import the module to test
from {module_path.replace('/', '.').replace('.py', '')} import *


class Test{module_name.title().replace('_', '')}:
    """Test cases for {module_name}"""
    
    @pytest.fixture
    def setup(self):
        """Setup test fixtures"""
        # Add any setup needed
        pass
    
    def test_initialization(self, setup):
        """Test module initialization"""
        # TODO: Add initialization tests
        assert True
    
    @pytest.mark.asyncio
    async def test_async_function(self, setup):
        """Test async functions"""
        # TODO: Add async tests
        assert True
    
    def test_error_handling(self, setup):
        """Test error handling"""
        # TODO: Add error handling tests
        with pytest.raises(Exception):
            pass
    
    def test_edge_cases(self, setup):
        """Test edge cases"""
        # TODO: Add edge case tests
        assert True
'''
    
    return template

def create_missing_tests(files_info):
    """Create test files for modules with low coverage"""
    tests_created = 0
    
    for file_info in files_info[:5]:  # Create tests for top 5 files
        module_path = file_info['path']
        
        # Convert module path to test path
        # app/agents/tools.py -> tests/test_agents_tools.py
        parts = module_path.split('/')
        if parts[0] in ['app', 'core']:
            test_name = 'test_' + '_'.join(parts[1:]).replace('.py', '.py')
            test_path = Path(f'/workspace/langchain_api/tests/{test_name}')
            
            if not test_path.exists():
                print(f"📝 Creating test for {module_path}")
                test_content = generate_test_template(module_path)
                
                test_path.parent.mkdir(parents=True, exist_ok=True)
                with open(test_path, 'w') as f:
                    f.write(test_content)
                
                tests_created += 1
                print(f"   ✅ Created {test_path}")
    
    return tests_created

def print_coverage_report(files_info):
    """Print formatted coverage report"""
    print("\n" + "="*70)
    print("📊 TEST COVERAGE ANALYSIS")
    print("="*70)
    
    if not files_info:
        print("✅ All files have coverage >= 80%!")
        return
    
    print(f"\n⚠️  {len(files_info)} files need improved coverage:\n")
    
    for i, file_info in enumerate(files_info[:10], 1):
        print(f"{i}. {file_info['path']}")
        print(f"   Coverage: {file_info['coverage']:.1f}%")
        print(f"   Missing lines: {file_info['missing_lines']}")
        if file_info['missing']:
            print(f"   First missing: {file_info['missing'][:5]}...")
        print()
    
    if len(files_info) > 10:
        print(f"... and {len(files_info) - 10} more files")

def suggest_improvements():
    """Suggest specific improvements for test coverage"""
    print("\n💡 Recommendations to improve coverage:")
    print("1. Focus on testing error handling paths")
    print("2. Add tests for edge cases and boundary conditions")
    print("3. Mock external dependencies (OpenAI, Neo4j, etc)")
    print("4. Test both success and failure scenarios")
    print("5. Use parametrized tests for multiple inputs")
    print("\nExample parametrized test:")
    print("""
@pytest.mark.parametrize("input,expected", [
    ("valid", True),
    ("", False),
    (None, False),
    ("special!@#", False),
])
def test_validation(input, expected):
    assert validate(input) == expected
""")

def main():
    print("🎯 Test Coverage Improvement Tool\n")
    
    # Check if we're in the right directory
    if not Path("/workspace/langchain_api").exists():
        print("❌ Error: Run this script from the project root")
        sys.exit(1)
    
    # Run coverage analysis
    success = run_coverage_report()
    
    if not success:
        print("\n⚠️  Some tests failed. Fix failing tests first.")
    
    # Analyze coverage
    files_info = analyze_coverage()
    
    # Print report
    print_coverage_report(files_info)
    
    # Create missing tests
    if files_info:
        response = input("\n📝 Create test templates for low coverage files? (y/n): ")
        if response.lower() == 'y':
            created = create_missing_tests(files_info)
            print(f"\n✅ Created {created} test files")
    
    # Suggest improvements
    suggest_improvements()
    
    # Final summary
    if files_info:
        avg_coverage = sum(f['coverage'] for f in files_info) / len(files_info)
        print(f"\n📈 Average coverage for files < 80%: {avg_coverage:.1f}%")
        print(f"📊 Files needing improvement: {len(files_info)}")
    
    print("\n✨ Next steps:")
    print("1. Fill in the TODO sections in generated tests")
    print("2. Run 'pytest tests/ -v' to verify tests pass")
    print("3. Run this script again to check improvements")

if __name__ == '__main__':
    main()