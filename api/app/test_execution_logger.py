import os
import time
import shutil
import tempfile
from core.execution_logger import ExecutionLogger, ExecutionCacheManager

def test_execution_logger_async():
    with tempfile.TemporaryDirectory() as tmp_dir:
        city_key = "testcity"
        scenario_id = "test_scen_101"
        logger = ExecutionLogger(tmp_dir, city_key, scenario_id)
        
        # Test phase switching and logging
        logger.set_phase("01_recommendation")
        t0 = time.time()
        for i in range(1000):
            logger.log(f"Candidate {i} evaluated with CER {i*0.1:.4f}")
        t1 = time.time()
        
        # Assert non-blocking enqueue time (<100ms for 1000 items)
        assert (t1 - t0) < 0.2, f"Logging 1000 items took too long: {t1-t0:.4f}s"
        
        logger.set_phase("02_ingestion_and_topology")
        logger.log("Ingesting PostGIS tables...")
        
        # Close and flush
        logger.close()
        
        # Check files on disk
        rec_log = os.path.join(tmp_dir, city_key, "logs", scenario_id, "01_recommendation.log")
        ing_log = os.path.join(tmp_dir, city_key, "logs", scenario_id, "02_ingestion_and_topology.log")
        
        assert os.path.exists(rec_log), "01_recommendation.log was not created"
        assert os.path.exists(ing_log), "02_ingestion_and_topology.log was not created"
        
        with open(rec_log, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 1000, f"Expected 1000 lines in rec_log, got {len(lines)}"

        print("✅ test_execution_logger_async PASSED!")

def test_execution_cache_manager():
    with tempfile.TemporaryDirectory() as tmp_dir:
        city_key = "testcity"
        logs_root = os.path.join(tmp_dir, city_key, "logs")
        
        # Create dummy scenario folders
        os.makedirs(os.path.join(logs_root, "baseline"), exist_ok=True)
        os.makedirs(os.path.join(logs_root, "rec_12345"), exist_ok=True)
        os.makedirs(os.path.join(logs_root, "temp_run_99"), exist_ok=True)
        
        # Purge temporary logs
        ExecutionCacheManager.purge_temporary_logs(tmp_dir, city_key)
        
        remaining = os.listdir(logs_root)
        assert "baseline" in remaining, "baseline folder was incorrectly purged"
        assert "rec_12345" in remaining, "rec_12345 folder was incorrectly purged"
        assert "temp_run_99" not in remaining, "temp_run_99 folder was not purged"
        
        print("✅ test_execution_cache_manager PASSED!")

if __name__ == "__main__":
    test_execution_logger_async()
    test_execution_cache_manager()
