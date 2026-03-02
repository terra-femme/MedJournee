# guardrails/audio_deletion_enforcer.py
"""
AUDIO DELETION ENFORCER GUARDRAIL

Priority: 2 (high - privacy promise)

Ensures all audio files are deleted after processing to fulfill
MedJournee's privacy promise. Tracks registered audio files and
verifies/forces deletion at pipeline end.

Features:
- Track all audio files registered during pipeline
- Verify files are deleted after processing
- Force delete any remaining files at pipeline end
- Audit log of all deletion actions
"""

import os
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Set
from dataclasses import dataclass, field

from guardrails.base import (
    BaseGuardrail,
    GuardrailContext,
    GuardrailResult,
    GuardrailAction
)


@dataclass
class AudioFileRecord:
    """Record of a tracked audio file"""
    file_path: str
    session_id: str
    registered_at: str = field(default_factory=lambda: datetime.now().isoformat())
    deleted_at: Optional[str] = None
    deletion_verified: bool = False
    error: Optional[str] = None


@dataclass
class DeletionAuditLog:
    """Audit log entry for deletion actions"""
    session_id: str
    action: str  # "registered", "deleted", "force_deleted", "verified", "failed"
    file_path: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    details: Dict = field(default_factory=dict)


class AudioDeletionEnforcer(BaseGuardrail):
    """
    Guardrail that ensures audio files are deleted after processing.

    This guardrail maintains a registry of audio files and ensures they
    are properly cleaned up. It runs at the END of the pipeline to
    verify all tracked files have been deleted.
    """

    NAME = "audio_deletion_enforcer"
    PRIORITY = 2  # High priority - privacy
    DESCRIPTION = "Ensures audio files are deleted after processing"

    def __init__(self, enabled: bool = True, force_delete: bool = True):
        """
        Initialize audio deletion enforcer.

        Args:
            enabled: Whether this guardrail is active
            force_delete: If True, force delete any remaining files
        """
        super().__init__(enabled)
        self.force_delete = force_delete

        # Registry: session_id -> set of file paths
        self._registry: Dict[str, Set[str]] = {}

        # File records for detailed tracking
        self._file_records: Dict[str, AudioFileRecord] = {}

        # Audit log
        self._audit_log: List[DeletionAuditLog] = []

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def register_audio_file(self, session_id: str, file_path: str) -> None:
        """
        Register an audio file for tracking.

        Call this when an audio file is created or received.

        Args:
            session_id: Session identifier
            file_path: Path to the audio file
        """
        async with self._lock:
            # Initialize session registry if needed
            if session_id not in self._registry:
                self._registry[session_id] = set()

            # Add to registry
            self._registry[session_id].add(file_path)

            # Create detailed record
            self._file_records[file_path] = AudioFileRecord(
                file_path=file_path,
                session_id=session_id
            )

            # Audit log
            self._audit_log.append(DeletionAuditLog(
                session_id=session_id,
                action="registered",
                file_path=file_path
            ))

    async def mark_deleted(self, file_path: str) -> None:
        """
        Mark a file as deleted (called by the component that deletes it).

        Args:
            file_path: Path to the deleted file
        """
        async with self._lock:
            if file_path in self._file_records:
                record = self._file_records[file_path]
                record.deleted_at = datetime.now().isoformat()

                self._audit_log.append(DeletionAuditLog(
                    session_id=record.session_id,
                    action="deleted",
                    file_path=file_path
                ))

    async def check(self, context: GuardrailContext) -> GuardrailResult:
        """
        Check if all audio files for a session have been deleted.

        This should be called at the END of the pipeline.

        Args:
            context: Context with session_id to check

        Returns:
            GuardrailResult indicating deletion status
        """
        session_id = context.session_id

        async with self._lock:
            # Get registered files for this session
            registered_files = self._registry.get(session_id, set())

            if not registered_files:
                return self._allow("No audio files registered for session")

            # Check each file
            remaining_files = []
            verified_deleted = []

            for file_path in registered_files:
                if os.path.exists(file_path):
                    remaining_files.append(file_path)
                else:
                    verified_deleted.append(file_path)
                    # Update record
                    if file_path in self._file_records:
                        self._file_records[file_path].deletion_verified = True

            # All files deleted?
            if not remaining_files:
                return self._allow(
                    message=f"All {len(verified_deleted)} audio files verified deleted",
                    verified_count=len(verified_deleted)
                )

            # Some files remain
            return self._warn(
                message=f"{len(remaining_files)} audio files not yet deleted",
                remaining_files=remaining_files,
                verified_deleted=len(verified_deleted)
            )

    async def enforce(self, context: GuardrailContext) -> GuardrailResult:
        """
        Enforce audio deletion - verify and force delete if enabled.

        Args:
            context: Context with session_id

        Returns:
            GuardrailResult with enforcement status
        """
        if not self.enabled:
            return self._allow("Guardrail disabled")

        # First, check current status
        result = await self.check(context)

        # If all files are deleted, we're done
        if result.action == GuardrailAction.ALLOW:
            return result

        # Files remain - force delete if enabled
        if self.force_delete and result.details.get("remaining_files"):
            force_deleted = []
            failed_deletions = []

            for file_path in result.details["remaining_files"]:
                try:
                    await self._force_delete_file(file_path, context.session_id)
                    force_deleted.append(file_path)
                except Exception as e:
                    failed_deletions.append({"file": file_path, "error": str(e)})

            if failed_deletions:
                return self._block(
                    message=f"Failed to delete {len(failed_deletions)} audio files",
                    force_deleted=force_deleted,
                    failed=failed_deletions
                )

            return self._allow(
                message=f"Force deleted {len(force_deleted)} remaining audio files",
                force_deleted=force_deleted
            )

        # Force delete disabled - return warning
        return result

    async def _force_delete_file(self, file_path: str, session_id: str) -> None:
        """
        Force delete an audio file.

        Args:
            file_path: Path to delete
            session_id: Session for audit logging
        """
        try:
            # Double-check it's an audio file (safety check)
            path = Path(file_path)
            audio_extensions = {'.webm', '.mp3', '.mp4', '.wav', '.m4a', '.ogg', '.flac'}

            if path.suffix.lower() not in audio_extensions:
                raise ValueError(f"Not an audio file: {file_path}")

            # Delete the file
            os.unlink(file_path)

            # Update records
            async with self._lock:
                if file_path in self._file_records:
                    record = self._file_records[file_path]
                    record.deleted_at = datetime.now().isoformat()
                    record.deletion_verified = True

                self._audit_log.append(DeletionAuditLog(
                    session_id=session_id,
                    action="force_deleted",
                    file_path=file_path
                ))

        except Exception as e:
            async with self._lock:
                if file_path in self._file_records:
                    self._file_records[file_path].error = str(e)

                self._audit_log.append(DeletionAuditLog(
                    session_id=session_id,
                    action="failed",
                    file_path=file_path,
                    details={"error": str(e)}
                ))
            raise

    async def cleanup_session(self, session_id: str) -> Dict:
        """
        Clean up all tracking data for a session.

        Call this after pipeline completion.

        Args:
            session_id: Session to clean up

        Returns:
            Summary of cleanup actions
        """
        async with self._lock:
            # Get session files
            files = self._registry.pop(session_id, set())

            # Remove file records
            for file_path in files:
                self._file_records.pop(file_path, None)

            return {
                "session_id": session_id,
                "files_tracked": len(files),
                "cleaned_up": True
            }

    def get_audit_log(self, session_id: Optional[str] = None) -> List[Dict]:
        """
        Get audit log entries.

        Args:
            session_id: Optional filter by session

        Returns:
            List of audit log entries
        """
        if session_id:
            return [
                {
                    "session_id": entry.session_id,
                    "action": entry.action,
                    "file_path": entry.file_path,
                    "timestamp": entry.timestamp,
                    "details": entry.details
                }
                for entry in self._audit_log
                if entry.session_id == session_id
            ]

        return [
            {
                "session_id": entry.session_id,
                "action": entry.action,
                "file_path": entry.file_path,
                "timestamp": entry.timestamp,
                "details": entry.details
            }
            for entry in self._audit_log
        ]


# Global instance for use across the pipeline
_enforcer: Optional[AudioDeletionEnforcer] = None


def get_audio_deletion_enforcer() -> AudioDeletionEnforcer:
    """Get or create the global audio deletion enforcer."""
    global _enforcer
    if _enforcer is None:
        _enforcer = AudioDeletionEnforcer()
    return _enforcer


# Convenience functions
async def register_audio(session_id: str, file_path: str) -> None:
    """Register an audio file for deletion tracking."""
    enforcer = get_audio_deletion_enforcer()
    await enforcer.register_audio_file(session_id, file_path)


async def verify_audio_deleted(session_id: str) -> GuardrailResult:
    """Verify all audio files for a session have been deleted."""
    enforcer = get_audio_deletion_enforcer()
    context = GuardrailContext(session_id=session_id)
    return await enforcer.enforce(context)
