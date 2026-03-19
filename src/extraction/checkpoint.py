"""
Checkpoint management for batch PDF processing.

Tracks processed files, failed files, and resume state.
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any


class CheckpointManager:
    """
    Manages checkpoint state for batch PDF processing.
    
    Tracks:
    - Which files have been processed
    - Which files are partially processed
    - Which files failed
    - Which files were skipped
    """
    
    def __init__(self, checkpoint_path: str, project_name: str):
        """
        Initialize checkpoint manager.
        
        Args:
            checkpoint_path: Path to checkpoint JSON file
            project_name: Name of the current project/batch
        """
        self.checkpoint_path = Path(checkpoint_path)
        self.project_name = project_name
        self.checkpoint_dir = self.checkpoint_path.parent
        
        # Thread lock for parallel safety
        self._lock = threading.Lock()
        
        # Ensure checkpoint directory exists
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        # Load or create checkpoint
        self.data = self._load_checkpoint()
    
    def _load_checkpoint(self) -> Dict:
        """Load checkpoint data from file or create new."""
        if self.checkpoint_path.exists():
            try:
                with open(self.checkpoint_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Could not load checkpoint: {e}. Starting fresh.")
        
        # Create new checkpoint
        return {
            "project": self.project_name,
            "started_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "processed_files": {},
            "failed_files": {},
            "skipped_files": {},
            "in_progress_files": {}
        }
    
    def _save_checkpoint(self):
        """Save checkpoint data to file (thread-safe with retry)."""
        import time
        import uuid
        
        with self._lock:
            self.data["last_updated"] = datetime.now().isoformat()
            
            # Retry logic for concurrent writes
            max_retries = 3
            for attempt in range(max_retries):
                temp_path = None
                try:
                    # Use unique temp file per save attempt
                    temp_path = self.checkpoint_path.with_suffix(f'.tmp.{uuid.uuid4().hex}')
                    
                    # Write to temp file with fsync for durability
                    with open(temp_path, 'w', encoding='utf-8') as f:
                        json.dump(self.data, f, indent=2, ensure_ascii=False)
                        f.flush()
                        os.fsync(f.fileno())
                    
                    # Atomic rename (cross-platform)
                    if os.name == 'nt':  # Windows
                        # Windows: remove target first if exists
                        if self.checkpoint_path.exists():
                            self.checkpoint_path.unlink()
                        temp_path.rename(self.checkpoint_path)
                    else:
                        # Unix: atomic replace
                        temp_path.replace(self.checkpoint_path)
                    
                    # Success - clean up and return
                    if temp_path.exists():
                        try:
                            temp_path.unlink()
                        except:
                            pass  # Ignore cleanup errors
                    return
                    
                except Exception as e:
                    # Clean up temp file
                    if temp_path and temp_path.exists():
                        try:
                            temp_path.unlink()
                        except:
                            pass
                    
                    # Retry with exponential backoff
                    if attempt < max_retries - 1:
                        time.sleep(0.1 * (2 ** attempt))
                    else:
                        # Log error but don't crash the whole process
                        print(f"Warning: Failed to save checkpoint after {max_retries} attempts: {e}")
                        # Don't raise - let processing continue
    
    def is_processed(self, pdf_path: str) -> bool:
        """Check if a file has been completely processed."""
        filename = Path(pdf_path).name
        return filename in self.data["processed_files"]
    
    def get_partial_progress(self, pdf_path: str) -> Optional[Dict]:
        """Get progress for partially processed file."""
        filename = Path(pdf_path).name
        return self.data["in_progress_files"].get(filename)
    
    def get_last_processed_page(self, pdf_path: str) -> int:
        """Get the last successfully processed page number."""
        filename = Path(pdf_path).name
        progress = self.data["in_progress_files"].get(filename)
        if progress:
            return progress.get("last_page", 0)
        return 0
    
    def mark_page_processed(self, pdf_path: str, page_num: int, total_pages: int):
        """Mark a single page as processed."""
        filename = Path(pdf_path).name
        
        if filename not in self.data["in_progress_files"]:
            self.data["in_progress_files"][filename] = {
                "total_pages": total_pages,
                "pages_done": 0,
                "last_page": 0,
                "started_at": datetime.now().isoformat()
            }
        
        self.data["in_progress_files"][filename]["pages_done"] += 1
        self.data["in_progress_files"][filename]["last_page"] = page_num
        
        self._save_checkpoint()
    
    def mark_file_complete(self, pdf_path: str):
        """Mark entire file as completely processed."""
        filename = Path(pdf_path).name
        
        # Move from in_progress to processed
        if filename in self.data["in_progress_files"]:
            progress = self.data["in_progress_files"].pop(filename)
            self.data["processed_files"][filename] = {
                "status": "complete",
                "total_pages": progress.get("total_pages", 0),
                "completed_at": datetime.now().isoformat()
            }
        else:
            self.data["processed_files"][filename] = {
                "status": "complete",
                "completed_at": datetime.now().isoformat()
            }
        
        self._save_checkpoint()
    
    def mark_file_failed(self, pdf_path: str, error: str, stage: str = "unknown"):
        """Mark file as failed with error message."""
        filename = Path(pdf_path).name
        
        # Remove from in_progress if it was there
        if filename in self.data["in_progress_files"]:
            del self.data["in_progress_files"][filename]
        
        self.data["failed_files"][filename] = {
            "error": error,
            "stage": stage,
            "failed_at": datetime.now().isoformat()
        }
        
        self._save_checkpoint()
    
    def mark_file_skipped(self, pdf_path: str, reason: str, extra_info: Optional[Dict] = None):
        """Mark file as skipped with reason."""
        filename = Path(pdf_path).name
        
        skip_info = {
            "reason": reason,
            "skipped_at": datetime.now().isoformat()
        }
        
        if extra_info:
            skip_info.update(extra_info)
        
        self.data["skipped_files"][filename] = skip_info
        self._save_checkpoint()
    
    def get_stats(self) -> Dict[str, int]:
        """Get processing statistics."""
        return {
            "processed": len(self.data["processed_files"]),
            "failed": len(self.data["failed_files"]),
            "skipped": len(self.data["skipped_files"]),
            "in_progress": len(self.data["in_progress_files"])
        }
    
    def get_failed_files(self) -> Dict[str, Dict]:
        """Get all failed files with their error messages."""
        return self.data["failed_files"].copy()
    
    def get_skipped_files(self) -> Dict[str, Dict]:
        """Get all skipped files with their reasons."""
        return self.data["skipped_files"].copy()
    
    def reset_file(self, pdf_path: str):
        """Reset a file to reprocess it."""
        filename = Path(pdf_path).name
        
        # Remove from all tracking
        for key in ["processed_files", "failed_files", "skipped_files", "in_progress_files"]:
            if filename in self.data[key]:
                del self.data[key][filename]
        
        self._save_checkpoint()
    
    def reset_all(self):
        """Reset entire checkpoint (use with caution!)."""
        self.data = {
            "project": self.project_name,
            "started_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "processed_files": {},
            "failed_files": {},
            "skipped_files": {},
            "in_progress_files": {}
        }
        self._save_checkpoint()
