"""Test execution helpers with structured logging and reporting support."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional
import unittest

_LOGGER_NAME = "autowebtest.runner"


def _create_logger(log_file: Path) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)

    # Clear existing handlers to avoid duplicate logs when run repeatedly.
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


class LoggingTestResult(unittest.TextTestResult):
    """Custom unittest result class that forwards events to a logger."""

    def __init__(self, *args, logger: logging.Logger, **kwargs):
        super().__init__(*args, **kwargs)
        self._logger = logger

    def startTest(self, test: unittest.case.TestCase) -> None:
        self._logger.info("开始执行测试用例: %s", test.id())
        super().startTest(test)

    def addSuccess(self, test: unittest.case.TestCase) -> None:
        self._logger.info("测试用例通过: %s", test.id())
        super().addSuccess(test)

    def addFailure(self, test: unittest.case.TestCase, err) -> None:  # type: ignore[override]
        self._logger.error("测试用例失败: %s", test.id(), exc_info=err)
        super().addFailure(test, err)

    def addError(self, test: unittest.case.TestCase, err) -> None:  # type: ignore[override]
        self._logger.error("测试用例报错: %s", test.id(), exc_info=err)
        super().addError(test, err)

    def addSkip(self, test: unittest.case.TestCase, reason: str) -> None:
        self._logger.warning("测试用例跳过: %s 原因: %s", test.id(), reason)
        super().addSkip(test, reason)


class LoggingTestRunner(unittest.TextTestRunner):
    """Test runner that logs execution details."""

    def __init__(self, *args, logger: logging.Logger, **kwargs):
        super().__init__(*args, resultclass=self._make_result_class(logger), **kwargs)
        self._logger = logger

    @staticmethod
    def _make_result_class(logger: logging.Logger):
        class _Result(LoggingTestResult):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, logger=logger, **kwargs)

        return _Result


class TestReport:
    """Structured summary of a unittest run."""

    def __init__(self, result: unittest.TestResult, *, start_time: datetime, end_time: datetime, log_file: Path):
        self.result = result
        self.start_time = start_time
        self.end_time = end_time
        self.log_file = log_file

    @property
    def total(self) -> int:
        return self.result.testsRun

    @property
    def failures(self) -> int:
        return len(self.result.failures)

    @property
    def errors(self) -> int:
        return len(self.result.errors)

    @property
    def skipped(self) -> int:
        return len(getattr(self.result, "skipped", []))

    @property
    def expected_failures(self) -> int:
        return len(getattr(self.result, "expectedFailures", []))

    @property
    def unexpected_successes(self) -> int:
        return len(getattr(self.result, "unexpectedSuccesses", []))

    @property
    def passed(self) -> int:
        return (
            self.total
            - self.failures
            - self.errors
            - self.unexpected_successes
            - self.expected_failures
            - self.skipped
        )

    @property
    def pass_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return round(self.passed / self.total, 4)

    def to_dict(self) -> dict:
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": round((self.end_time - self.start_time).total_seconds(), 3),
            "log_file": str(self.log_file),
            "summary": {
                "total": self.total,
                "passed": self.passed,
                "failed": self.failures,
                "errors": self.errors,
                "skipped": self.skipped,
                "expected_failures": self.expected_failures,
                "unexpected_successes": self.unexpected_successes,
                "pass_rate": self.pass_rate,
            },
            "has_error": self.errors > 0,
        }

    def write_json(self, report_file: Path) -> None:
        content = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
        report_file.write_text(f"{content}\n", encoding="utf-8")

    def write_markdown(self, report_file: Path) -> None:
        data = self.to_dict()
        summary_lines = [
            "# 测试报告",
            "",
            f"- 开始时间: {data['start_time']}",
            f"- 结束时间: {data['end_time']}",
            f"- 执行时长: {data['duration_seconds']} 秒",
            f"- 运行日志: {data['log_file']}",
            "",
            "## 用例统计",
            "",
            "| 指标 | 数值 |",
            "| ---- | ---- |",
        ]
        summary = data["summary"]
        summary_lines.extend(
            [
                f"| 用例总数 | {summary['total']} |",
                f"| 通过数量 | {summary['passed']} |",
                f"| 失败数量 | {summary['failed']} |",
                f"| 错误数量 | {summary['errors']} |",
                f"| 跳过数量 | {summary['skipped']} |",
                f"| 预期失败 | {summary['expected_failures']} |",
                f"| 意外通过 | {summary['unexpected_successes']} |",
                f"| 通过率 | {summary['pass_rate'] * 100:.2f}% |",
            ]
        )
        summary_lines.append("")
        summary_lines.append(f"- 是否存在错误: {'是' if data['has_error'] else '否'}")
        report_file.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


def run_test_suite(
    test_modules: Optional[Iterable[str]] = None,
    *,
    test_path: str = "tests",
    reports_dir: str = "reports",
    logs_dir: str = "logs",
) -> TestReport:
    """Run tests and produce log and report files.

    Args:
        test_modules: Optional explicit modules to load. When omitted unittest discovery is used.
        test_path: Test discovery path.
        reports_dir: Directory for generated reports.
        logs_dir: Directory for generated logs.

    Returns:
        TestReport: Structured report for the executed suite.
    """

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    logs_path = Path(logs_dir)
    reports_path = Path(reports_dir)
    logs_path.mkdir(parents=True, exist_ok=True)
    reports_path.mkdir(parents=True, exist_ok=True)

    log_file = logs_path / f"test_run_{timestamp}.log"
    logger = _create_logger(log_file)

    logger.info("开始执行自动化测试流程")
    start_time = datetime.now()

    if test_modules:
        suite = unittest.TestSuite()
        loader = unittest.defaultTestLoader
        for module in test_modules:
            logger.info("加载测试模块: %s", module)
            suite.addTests(loader.loadTestsFromName(module))
    else:
        logger.info("通过路径发现测试用例: %s", test_path)
        loader = unittest.defaultTestLoader
        suite = loader.discover(start_dir=test_path)

    runner = LoggingTestRunner(verbosity=2, logger=logger)
    result = runner.run(suite)

    end_time = datetime.now()
    logger.info("自动化测试流程结束")

    report = TestReport(result, start_time=start_time, end_time=end_time, log_file=log_file)

    json_file = reports_path / f"test_report_{timestamp}.json"
    md_file = reports_path / f"test_report_{timestamp}.md"
    report.write_json(json_file)
    report.write_markdown(md_file)

    # Also maintain a latest report pointer for quick access.
    latest_json = reports_path / "latest_report.json"
    latest_md = reports_path / "latest_report.md"
    report.write_json(latest_json)
    report.write_markdown(latest_md)

    logger.info(
        "测试执行完成: 总数=%s, 通过=%s, 失败=%s, 错误=%s, 通过率=%.2f%%",
        report.total,
        report.passed,
        report.failures,
        report.errors,
        report.pass_rate * 100,
    )
    logger.info("测试报告已生成: %s", json_file)
    logger.info("Markdown 报告已生成: %s", md_file)

    return report
