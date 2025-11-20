
import json
import os
from typing import List, Dict
import requests
import xml.etree.ElementTree as ET
from logger import log

class CVEProcessor:
    def __init__(self, cve_id: str, adaptation_file: str = "/PoCAdaptation/exploit/Adaptation.json"):
        self.cve_id = cve_id
        self.adaptation_file = adaptation_file
        self.cve_data = self._load_cve_data()
        self.reproduced_versions = []
        self.affected_versions = []
        self.all_maven_versions = [] 
        self.group_id = ''
        self.artifact_id = ''
        self.reproduced_behavior = ''
        self.reproduced_detail = []
        self.repository_url = ''
        self.owner = ''
        self.repo = ''

    def _load_cve_data(self) -> Dict:
        if not os.path.exists(self.adaptation_file):
            log("Analyzer", f"Adaptation file not found: {self.adaptation_file}", "error")
            raise FileNotFoundError(f"Adaptation file not found: {self.adaptation_file}")

        with open(self.adaptation_file, "r") as f:
            data = json.load(f)

        for entry in data:
            if entry.get("CVE") == self.cve_id:
                return entry

        log("Analyzer", f"CVE ID {self.cve_id} not found in {self.adaptation_file}", "error")
        raise ValueError(f"CVE ID {self.cve_id} not found in {self.adaptation_file}")

    def identify_reproduced_versions(self):
        affected = set(self.cve_data.get("affected", []))
        required = set(self.cve_data.get("requiredAdaptVersions", []))
        self.group_id = self.cve_data.get("groupId")
        self.artifact_id = self.cve_data.get("artifactId")
        self.reproduced_behavior = self.cve_data.get("reproducedBehavior")
        self.reproduced_detail = set(self.cve_data.get("reproducedDetail", []))
        self.repository_url = self.cve_data.get("repositoryUrl")
        self.owner = self.cve_data.get("owner")
        self.repo = self.cve_data.get("repo")
        self.affected_versions = affected
        self.reproduced_versions = [v for v in self.all_maven_versions if v in (affected - required)]
    
    def get_group_id(self) -> str:
        return self.group_id
    
    def get_artifact_id(self) -> str:
        return self.artifact_id
    
    def get_cve_id(self) -> str:
        return self.cve_id

    def get_owner(self) -> str:
        return self.owner
    
    def get_repo(self) -> str:
        return self.repo
    
    def get_reproduced_behavior(self) -> str:
        return self.reproduced_behavior

    def get_reproduced_detail(self) -> List[str]:
        return self.reproduced_detail

    def get_reproduced_versions(self) -> List[str]:
        return self.reproduced_versions
    
    def get_affected_versions(self) -> List[str]:
        return self.affected_versions
    
    def get_repository_url(self) -> str:
        return self.repository_url

    def fetch_all_maven_versions(self):
        group_id = self.cve_data["groupId"]
        artifact_id = self.cve_data["artifactId"]
        cache_dir = "/PoCAdaptation/library"
        os.makedirs(cache_dir, exist_ok=True)

        cache_filename = f"{group_id.replace('.', '_')}_{artifact_id}.txt"
        cache_path = os.path.join(cache_dir, cache_filename)

        if os.path.exists(cache_path):
            log("Analyzer", f"Loading cached versions from: {cache_path}", "info")
            with open(cache_path, "r") as f:
                versions = [line.strip() for line in f if line.strip()]
            self.all_maven_versions = versions
            log("Analyzer", f"{group_id}:{artifact_id} has {len(versions)} versions (cached).", "info")
            return


        metadata_url = f"https://repo.maven.apache.org/maven2/{group_id.replace('.', '/')}/{artifact_id}/maven-metadata.xml"
        log("Analyzer", f"Fetching: {metadata_url}", "info")
        versions = self._fetch_versions_from_metadata(metadata_url)
        self.all_maven_versions = versions
        log("Analyzer", f"{group_id}:{artifact_id} has {len(versions)} versions.", "info")


        try:
            with open(cache_path, "w") as f:
                for version in versions:
                    f.write(version + "\n")
            log("Analyzer", f"Saved versions to cache: {cache_path}", "info")
        except Exception as e:
            log("Analyzer", f"Failed to save cache file: {e}", "error")

    @staticmethod
    def _fetch_versions_from_metadata(metadata_url):
        try:
            response = requests.get(metadata_url, timeout=10)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                versions_node = root.find(".//versions")
                if versions_node is not None:
                    return [v.text for v in versions_node.findall("version")]
            else:
                log("Analyzer", f"Failed to fetch metadata: HTTP {response.status_code}", "warning")
        except Exception as e:
            log("Analyzer", f"Error fetching/parsing metadata: {e}", "error")
        return []

    def print_summary(self):
        log("Analyzer", f"CVE ID: {self.cve_id}", "info")
        log("Analyzer", "Successfully Reproduced Versions:", "info")
        for ver in self.reproduced_versions:
            log("Analyzer", f"  - {ver}", "info")
        if self.all_maven_versions:
            log("Analyzer", f"Total Maven Versions Found: {len(self.all_maven_versions)}", "info")
