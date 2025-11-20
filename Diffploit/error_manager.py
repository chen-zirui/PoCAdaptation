
import re
from typing import Dict, List
from collections import defaultdict
from logger import log  
from llm_client import LLMClient




class StructuredError:
    def __init__(self, file: str, line: int, column: int, message: str, symbol: str = None, location: str = None):
        self.file = file
        self.line = line
        self.column = column
        self.message = message
        self.symbol = symbol
        self.location = location
        self.code_line = None 

    def __repr__(self):
        code_preview = self.code_line.strip() if self.code_line else ''
        return (f"[{self.file}:{self.line},{self.column}] {self.message} | "
                f"{self.symbol or ''} @ {self.location or ''} | Code: {code_preview}")

    def __eq__(self, other):
        return isinstance(other, StructuredError) and (
            self.file, self.line, self.column, self.message, self.symbol, self.location
        ) == (
            other.file, other.line, other.column, other.message, other.symbol, other.location
        )

    def __hash__(self):
        return hash((self.file, self.line, self.column, self.message, self.symbol, self.location))


class ErrorManager:
    def __init__(self, error_log: str):
        self.raw_lines = self.extract_maven_error_lines(error_log)
        self.pending_errors: List[StructuredError] = []
        self.resolved_errors: List[StructuredError] = []

        self._parse_errors()
        self.sort_errors()
        self._load_code_lines()


    def extract_maven_error_lines(self, raw_log: str) -> List[str]:
        errors = []
        goal_match = re.search(r"\[ERROR\] Failed to execute goal.*", raw_log, re.DOTALL)
        if goal_match:
            errors += [line for line in goal_match.group(0).splitlines() if "[ERROR]" in line]
        if not errors:
            errors = [line for line in raw_log.splitlines() if "[ERROR]" in line]
        return errors

    def _parse_errors(self):
        current_error = None
        IGNORED_PATTERNS = [
            r"^\[ERROR\] Failed to execute goal .* on project .*: Compilation failure:.*",
            r"^\[ERROR\] Failed to execute goal .* on project .*: Compilation failure",
            r"^\[ERROR\] Failed to execute goal .* on project .*: There are test failures.",
            r"^\[ERROR\]$", 
            r"\[ERROR\] -> \[Help \d+\]",
            r"\[INFO\] .*",  
            r"\[WARNING\] .*",  
            r"\[ERROR\] For more information about the errors and possible solutions, please read.*",
            r"\[ERROR\] To see the full stack trace of the errors, re-run Maven with the -e switch.*",
            r"\[ERROR\] Re-run Maven using the -X switch to enable full debug logging.*",
            r"^\[ERROR\] \[Help \d+\]( .*)?$",  
            r"^\[ERROR\] Please refer to .*/surefire-reports.*$",
            r"^\[ERROR\] Please refer to dump files \(if any exist\) \[.*\]\.dump.*",
            
        ]

        fallback_error_line = None
        fallback_pattern = (
            r"Failed to execute goal org\.apache\.maven\.plugins:maven-surefire-plugin:[\d\.]+:test \(default-test\) on project .*: There are test failures\."
        )
        for line in self.raw_lines:
            if re.search(fallback_pattern, line):
                fallback_error_line = line.strip()
                break
                      
        for line in self.raw_lines:
            line = line.strip()            
            match = re.match(r'\[ERROR\] (.*?):\[(\d+),(\d+)\] (.+)', line)
            if any(re.match(pattern, line) for pattern in IGNORED_PATTERNS):
                log("ErrorManager", f"Ignoring line: {line}", "info")
                continue  

            log("ErrorManager", f"Processing line: {line}", "success")

            if match:
                if current_error is not None:
                    self.pending_errors.append(current_error)
                file, line_num, col_num, message = match.groups()
                current_error = StructuredError(
                    file.strip(), int(line_num), int(col_num), message.strip()
                )
                continue
            symbol_match = re.match(r'\[ERROR\]\s+symbol:\s+(.+)', line)
            if symbol_match and current_error is not None:
                current_error.symbol = symbol_match.group(1).strip()
                continue
            location_match = re.match(r'\[ERROR\]\s+location:\s+(.+)', line)
            if location_match and current_error is not None:
                current_error.location = location_match.group(1).strip()
                continue

            fallback_match = re.match(r'\[ERROR\]\s+(.*)', line)
            if fallback_match:
                message = fallback_match.group(1).strip()
                if current_error is None:
                    current_error = StructuredError("UNKNOWN", -1, -1, message)
                else:
                    current_error.message += " " + message
                continue
            
        if current_error is not None:
            self.pending_errors.append(current_error)
        self.pending_errors = list(set(self.pending_errors))


        if not self.pending_errors and fallback_error_line:
            log("ErrorManager", f"Using fallback error line: {fallback_error_line}", "info")
            self.pending_errors.append(
                StructuredError("UNKNOWN", -1, -1, fallback_error_line)
            )


    def sort_errors(self):
        self.pending_errors.sort(key=lambda e: (e.file, e.line, e.column))
        self.resolved_errors.sort(key=lambda e: (e.file, e.line, e.column))


    def _load_code_lines(self):
        file_line_map = defaultdict(set)
        for err in self.pending_errors:
            file_line_map[err.file].add(err.line)
        for file_path, lines in file_line_map.items():
            try:
                with open(file_path, encoding="utf-8") as f:
                    all_lines = f.readlines()
            except Exception as e:
                log("ErrorManager", f"Failed to read file {file_path}: {e}", "error")
                continue
            for err in filter(lambda e: e.file == file_path, self.pending_errors):
                if 1 <= err.line <= len(all_lines):
                    err.code_line = all_lines[err.line - 1].rstrip("\n")
                else:
                    err.code_line = None


    def get_errors_by_file(self, file: str) -> List[StructuredError]:
        return [e for e in self.pending_errors if e.file == file]

    def summary(self):
        return f"Pending: {len(self.pending_errors)} | Resolved: {len(self.resolved_errors)}"

    def debug_print(self):
        for e in self.pending_errors:
            log("ErrorManager", f"Pending Error: {e}", "info")
            log("ErrorManager", f"  File: {e.file}", "debug")
            log("ErrorManager", f"  Line: {e.line}", "debug")
            log("ErrorManager", f"  Column: {e.column}", "debug")
            log("ErrorManager", f"  Message: {e.message}", "debug")
            if e.symbol:
                log("ErrorManager", f"  Symbol: {e.symbol}", "debug")
            if e.location:
                log("ErrorManager", f"  Location: {e.location}", "debug")
            if e.code_line:
                log("ErrorManager", f"  Code Line: {e.code_line}", "debug")


    def group_errors_by_type(self):
        grouped = defaultdict(list)
        for err in self.pending_errors:
            key = f"{err.message} | {err.symbol or ''}".strip()
            grouped[key].append(err)
        return grouped
    

    def get_grouped_errors(self):
        grouped = self.group_errors_by_type()
        result = {}
        for group_key, errors in grouped.items():
            result[group_key] = []
            for e in errors:
                result[group_key].append({
                    "file": e.file,
                    "line": e.line,
                    "column": e.column,
                    "message": e.message,
                    "symbol": e.symbol,
                    "location": e.location,
                    "code_line": e.code_line
                })
        return result



    def re_extract_root_cause_from_llm(self, err, from_version, to_version, err_log, cause) -> List[str]:
        if 'There are test failures.' in err['message']:
            prompt = (
                f"You are given an error log when executing 'mvn test' in a project relying on a library with version {to_version}: \n\n"
                f"Error: {err_log} \n\n"
                f"The test executes as expected in {from_version} but not in {to_version}. \n\n"
                "Extract two key entities from the error log for searching related diffs \n\n"
                "The extracted entities should reflect code-level identifiers that are likely to appear in diffs. We prefer a simple entity.\n\n"
                f"Current cause: {cause} \n\n failed to catch, try simpler or other entities.\n\n"
                "Output each node as a `;`-separated list, with no explanations. \n\n"
            )
        else:
            prompt = (
                f"You are given an error log when executing 'mvn test' in version {to_version}: \n\n"
                f"Error: {err['message']}, {err['symbol']}, {err['location']} \n\n"
                f"The test executes as expected in {from_version} \n\n"
                f"Error code: {err['code_line']} \n\n"
                "Extract two key *entities* from the error for searching related diffs \n\n"
                "The extracted entities should reflect code-level identifiers that are likely to appear in source code or diffs. \n\n"
                 f"Current cause: {cause} \n\n failed to catch, try simpler or other entities.\n\n"
                "Output each node as a `;`-separated list, with no explanations. \n\n"
            )

        response = LLMClient().ask(prompt)
        
        with open('/PoCAdaptation/log.txt', 'a', encoding='utf-8') as f:
                f.write("-----extract error-----\n")
                f.write("=== Prompt ===\n")
                f.write(prompt + "\n")
                f.write("=== Response ===\n")
                f.write(response + "\n")
                f.write("----------\n") 


        entities = [e.strip() for e in response.split(';') if e.strip()]
        log("ErrorManager", f"Extracted key entities: {entities}", "info")
        return entities
    
    
    def extract_trace_from_llm(self,from_version, to_version, code, cve_process) -> List[str]:

        prompt = (
            f"You are given an vulnerability exploit in  {to_version}: \n\n"
            f"Code: {code} \n\n"
            f"Extract Call Graph of the API call in library {cve_process.get_group_id()}:{cve_process.get_artifact_id()}(at most 5) \n\n"
            "We use this information to collect diff files \n\n"
            "Output each API name as a `;`-separated list, with no explanations. Withour package name, parameter list. \n\n"
        )

        response = LLMClient().ask(prompt)
        
        with open('/PoCAdaptation/log.txt', 'a', encoding='utf-8') as f:
                f.write("-----extract error-----\n")
                f.write("=== Prompt ===\n")
                f.write(prompt + "\n")
                f.write("=== Response ===\n")
                f.write(response + "\n")
                f.write("----------\n") 


        entities = list(dict.fromkeys(
            e.strip().split('.')[-1] if '.' in e.strip() else e.strip()
            for e in response.split(';') if e.strip()
        ))

        log("ErrorManager", f"Extracted key entities: {entities}", "info")
        return entities
    
    
    def extract_root_cause_from_llm(self, err, from_version, to_version, err_log) -> List[str]:
        if 'There are test failures.' in err['message']:
            prompt = (
                f"You are given an error log when executing 'mvn test' in a project relying on a library with version {to_version}: \n\n"
                f"Error: {err_log} \n\n"
                f"The test executes as expected in {from_version} but not in {to_version}. \n\n"
                "Extract two key entities from the error log for searching related diffs. Your classname and method name should ignore package and parameter\n\n"
                "The extracted entities should reflect code-level identifiers that are likely to appear in diffs. We prefer a simple entity\n\n"
                "Output each node as a `;`-separated list, with no explanations. \n\n"
            )
        else:
            prompt = (
                f"You are given an error log when executing 'mvn test' in version {to_version}: \n\n"
                f"Error: {err['message']}, {err['symbol']}, {err['location']} \n\n"
                f"The test executes as expected in {from_version} \n\n"
                f"Error code: {err['code_line']} \n\n"
                "Extract two key *entities* from the error for searching related diffs \n\n"
                "The extracted entities should reflect code-level identifiers that are likely to appear in source code or diffs. \n\n"
                "Output each node as a `;`-separated list, with no explanations. \n\n"
            )

        response = LLMClient().ask(prompt)
        
        with open('/PoCAdaptation/log.txt', 'a', encoding='utf-8') as f:
                f.write("-----extract error-----\n")
                f.write("=== Prompt ===\n")
                f.write(prompt + "\n")
                f.write("=== Response ===\n")
                f.write(response + "\n")
                f.write("----------\n") 


        entities = [e.strip() for e in response.split(';') if e.strip()]
        log("ErrorManager", f"Extracted key entities: {entities}", "info")
        return entities

    
if __name__ == "__main__":
    # Example usage
    error_log = """
    [ERROR] Failed to execute goal org.apache.maven.plugins:maven-surefire-plugin:2.12.4:test (default-test) on project CVE-2022-1848: There are test failures.
    [ERROR] 
    [ERROR] Please refer to /PoCAdaptation/exploit/pending/CVE-2022-1848/1.21.1/exploit/target/surefire-reports for the individual test results.
    [ERROR] -> [Help 1]
    [ERROR] 
    [ERROR] To see the full stack trace of the errors, re-run Maven with the -e switch.
    [ERROR] Re-run Maven using the -X switch to enable full debug logging.
    [ERROR] 
    [ERROR] For more information about the errors and possible solutions, please read the following articles:
    [ERROR] [Help 1] http://cwiki.apache.org/confluence/display/MAVEN/MojoFailureException
    """
    error_mgr = ErrorManager(error_log)
    grouped = error_mgr.get_grouped_errors()
    
