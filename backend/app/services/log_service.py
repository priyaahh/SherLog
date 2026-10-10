"""
Log service handling log upload, validation, parsing, and database retrieval
"""

import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List
from fastapi import UploadFile, HTTPException, status
from app.services.incident_service import parse_object_id, IncidentService
from app.models.log import LogResponse

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 Megabytes
ALLOWED_EXTENSIONS = {".log", ".txt", ".json"}


class LogService:

    @staticmethod
    async def upload_log_file(incident_id: str, file: UploadFile, db) -> LogResponse:
        """
        Validate, parse, and save log file for an incident
        """
        # 1. Verify incident exists
        await IncidentService.get_incident_by_id(incident_id, db)
        
        # 2. Validate file extension
        filename = file.filename or "uploaded_file.log"
        _, ext = os.path.splitext(filename)
        if ext.lower() not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file extension '{ext}'. Only .log, .txt, and .json files are allowed."
            )
            
        # 3. Read up to MAX_FILE_SIZE + 1 bytes to prevent memory overload
        contents = await file.read(MAX_FILE_SIZE + 1)
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size exceeds maximum allowed limit of 5 MB."
            )
            
        if len(contents) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is empty (0 bytes)."
            )
            
        # 4. Decode content and split into lines
        try:
            text_str = contents.decode("utf-8", errors="replace")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to decode log file content: {e}"
            )
            
        lines = [line.strip() for line in text_str.splitlines() if line.strip()]
        if not lines:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Log file contains no valid non-empty lines."
            )
            
        now = datetime.now(timezone.utc)
        doc = {
            "incident_id": incident_id,
            "filename": filename,
            "total_entries": len(lines),
            "raw_content": lines,
            "uploaded_at": now
        }
        
        # Store in MongoDB 'logs' collection
        result = await db.logs.insert_one(doc)
        doc["_id"] = result.inserted_id
        
        logger.info(f"Uploaded log file '{filename}' ({len(lines)} entries) for incident '{incident_id}'")
        return LogResponse(
            id=str(result.inserted_id),
            incident_id=incident_id,
            filename=filename,
            total_entries=len(lines),
            raw_content=lines,
            uploaded_at=now
        )

    @staticmethod
    async def get_logs_by_incident(incident_id: str, db) -> LogResponse:
        """
        Retrieve log record associated with an incident
        """
        # Verify incident exists first
        await IncidentService.get_incident_by_id(incident_id, db)
        
        doc = await db.logs.find_one({"incident_id": incident_id})
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No logs uploaded yet for incident '{incident_id}'"
            )
            
        return LogResponse(
            id=str(doc["_id"]),
            incident_id=doc["incident_id"],
            filename=doc["filename"],
            total_entries=doc["total_entries"],
            raw_content=doc["raw_content"],
            uploaded_at=doc["uploaded_at"]
        )
