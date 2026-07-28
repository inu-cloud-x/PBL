import requests
import os
from pathlib import Path
from typing import List, Dict, Optional
import json

class IPFSClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 5001):
        self.base_url = f"http://{host}:{port}/api/v0"
        self.is_connected = False
        try:
            # Check connectivity with a simple version call
            response = requests.post(f"{self.base_url}/version", timeout=2)
            if response.status_code == 200:
                self.is_connected = True
            else:
                print(f"IPFS API returned status code {response.status_code}")
        except Exception as e:
            print(f"Error connecting to IPFS API: {e}")
            print(f"Hint: Ensure 'ipfs daemon' is running and accessible at {self.base_url}")

    def pin_directory(self, dir_path: Path) -> str:
        """
        Uploads a directory recursively to IPFS using the HTTP API.
        Returns the CID of the directory.
        """
        if not self.is_connected:
            raise ConnectionError("IPFS API not connected. Please check your daemon.")

        files_to_upload = []
        # We need to collect all files in the directory
        # The IPFS API expects files to be sent in a specific multipart format
        # for recursive directory addition.
        
        # We walk through the directory and add each file
        # The key is to use the relative path as the 'name' in the multipart form
        for root, _, files in os.walk(dir_path):
            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(dir_path.parent)
                
                # We read the file content
                with open(full_path, "rb") as f:
                    content = f.read()
                
                # Each file is a tuple: (name, (filename, content))
                # For directories, IPFS API is a bit tricky via requests
                # A simpler way for MVP: upload files individually or use the 'add' API
                # with the correct directory structure.
                files_to_upload.append(
                    ("file", (str(rel_path), content, "application/octet-stream"))
                )

        # POST /api/v0/add?recursive=true&pin=true
        # Note: requests handles the multipart/form-data boundary automatically
        response = requests.post(
            f"{self.base_url}/add",
            params={"recursive": "true", "pin": "true"},
            files=files_to_upload
        )

        if response.status_code != 200:
            raise Exception(f"IPFS add failed ({response.status_code}): {response.text}")

        # The response is a sequence of JSON objects, one for each file/directory
        # We need to find the one that corresponds to the root directory
        # It's usually the last one.
        lines = response.text.strip().split("\n")
        last_result = json.loads(lines[-1])
        return last_result["Hash"]

    def add_bytes(self, data: bytes) -> str:
        """Adds raw bytes to IPFS and returns the CID."""
        if not self.is_connected:
            raise ConnectionError("IPFS API not connected.")
            
        files = {"file": data}
        response = requests.post(f"{self.base_url}/add", files=files)
        
        if response.status_code != 200:
            raise Exception(f"IPFS add failed: {response.text}")
            
        return response.json()["Hash"]

    def fetch(self, cid: str, dest: Path):
        """Downloads a CID from IPFS to the destination path."""
        # Using /api/v0/get
        response = requests.post(
            f"{self.base_url}/get",
            params={"arg": cid, "archive": "true"}
        )
        
        if response.status_code != 200:
            raise Exception(f"IPFS get failed: {response.text}")
            
        # This returns a tar archive, but for MVP we might just want to use shell if needed
        # Or implement tar extraction. For now, we mainly need 'add'.
        with open(dest, "wb") as f:
            f.write(response.content)
