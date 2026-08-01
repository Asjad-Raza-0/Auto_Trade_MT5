import json
import os
import tempfile
import pytest
from unittest.mock import patch
from python_bot.config import Config
from python_bot.main import setup_logging, cmd_clean_logs, parse_args, build_config
from logging.handlers import RotatingFileHandler
import logging


def test_config_logging_defaults():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp.write(b"{}")
        tmp_path = tmp.name

    try:
        config = Config(config_file=tmp_path)
        assert config.log_max_mb == 10
        assert config.log_max_bytes == 10 * 1024 * 1024
        assert config.log_backup_count == 5
        assert "log_rotation" in config.describe()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_config_logging_env_overrides():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp.write(b"{}")
        tmp_path = tmp.name

    try:
        with patch.dict(os.environ, {"LOG_MAX_MB": "20", "LOG_BACKUP_COUNT": "3"}):
            config = Config(config_file=tmp_path)
            assert config.log_max_mb == 20
            assert config.log_max_bytes == 20 * 1024 * 1024
            assert config.log_backup_count == 3
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_setup_logging_uses_rotating_file_handler():
    with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as tmp:
        tmp_log = tmp.name

    try:
        setup_logging("INFO", tmp_log, max_bytes=5000, backup_count=2)
        root_logger = logging.getLogger()
        rotating_handlers = [h for h in root_logger.handlers if isinstance(h, RotatingFileHandler)]
        assert len(rotating_handlers) >= 1
        rfh = rotating_handlers[0]
        assert rfh.maxBytes == 5000
        assert rfh.backupCount == 2
    finally:
        logging.shutdown()
        if os.path.exists(tmp_log):
            os.remove(tmp_log)


def test_cmd_clean_logs():
    with tempfile.TemporaryDirectory() as tmp_dir:
        main_log = os.path.join(tmp_dir, "test_bot.log")
        backup_1 = os.path.join(tmp_dir, "test_bot.log.1")
        backup_2 = os.path.join(tmp_dir, "test_bot.log.2")

        with open(main_log, "w") as f:
            f.write("some log data\n")
        with open(backup_1, "w") as f:
            f.write("backup 1\n")
        with open(backup_2, "w") as f:
            f.write("backup 2\n")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as cfg_file:
            cfg_file.write(json.dumps({"general": {"log_file": main_log}}))
            cfg_path = cfg_file.name

        try:
            config = Config(config_file=cfg_path)
            ret = cmd_clean_logs(config)
            assert ret == 0
            assert os.path.getsize(main_log) == 0
            assert not os.path.exists(backup_1)
            assert not os.path.exists(backup_2)
        finally:
            if os.path.exists(cfg_path):
                os.remove(cfg_path)
