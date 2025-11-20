
import difflib
import os
from logger import log
import re
from typing import List, Optional, Tuple
from enum import Enum, auto
from Levenshtein import ratio



class DiffType(Enum):
    MODIFIED = auto()
    NEW_FILE = auto()
    DELETED_FILE = auto()
    

class DiffUnit:
    def __init__(self, file: str, hunk_header: str, content: List[str], diff_type: DiffType = DiffType.MODIFIED):
        self.file = file
        self.hunk_header = hunk_header  # e.g., @@ -10,6 +10,7 @@
        self.content = content  # lines in the hunk
        self.diff_type = diff_type
        
        
    def __repr__(self):
        return f"<DiffUnit file={self.file} hunk={self.hunk_header} lines={len(self.content)} type={self.diff_type.value}>"


class DiffManager:
    def __init__(self, diff_path: str):
        self.diff_path = diff_path
        self.diff_units: List[DiffUnit] = []
        self._load_diff()

    def _load_diff(self):
        if not os.path.exists(self.diff_path):
            log("DiffManager", f"Diff file not found: {self.diff_path}", "error")
            return

        with open(self.diff_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        current_file = None
        current_hunk = None
        current_content = []
        deleted_file_candidate = None
        current_diff_type = DiffType.MODIFIED
        
        for line in lines:
            if line.startswith("diff --git"):
                if current_file and current_hunk and current_content:
                    self.diff_units.append(DiffUnit(
                        current_file, current_hunk, current_content, diff_type=current_diff_type
                    ))
                current_file = None
                current_hunk = None
                current_content = []
                current_diff_type = DiffType.MODIFIED 
                deleted_file_candidate = None
                
            elif line.startswith("deleted file mode"):
                current_diff_type = DiffType.DELETED_FILE

            elif line.startswith("new file mode"):
                current_diff_type = DiffType.NEW_FILE
                
                

            elif line.startswith("--- a/"):
                deleted_file_candidate = line.strip().replace("--- a/", "")

            elif line.startswith("+++ b/"):
                current_file = line.strip().replace("+++ b/", "")
            
            elif line.startswith("+++ /dev/null"):           
                if  current_diff_type == DiffType.DELETED_FILE:
                    current_file = deleted_file_candidate
 
            
            elif line.startswith("@@"):
                if current_file and current_hunk and current_content:
                    self.diff_units.append(DiffUnit(current_file, current_hunk, current_content))
                current_hunk = line.strip()
                current_content = []
                
            elif current_hunk:
                current_content.append(line.rstrip())

        # save last one
        if current_file and current_hunk and current_content:
            self.diff_units.append(DiffUnit(current_file, current_hunk, current_content))

    def summary(self):
        log("DiffManager", f"Loaded {len(self.diff_units)} diff blocks from {self.diff_path}", "info")
        for i, d in enumerate(self.diff_units):
            log("DiffManager", f"  {i+1:02d}. File: {d.file}, Hunk: {d.hunk_header}", "info")


    def get_diff_by_id(self, diff_id: int) -> Optional[str]:

        if diff_id == None:
            return None
        
        if 0 <= diff_id < len(self.diff_units):
            diff = self.diff_units[diff_id]
            content = diff.content
            if isinstance(content, list):
                lines = content
            else:
                lines = content.splitlines()


            result_lines = []
            for line in lines:
                if line.startswith('+') and not line.startswith('+++'):
                    result_lines.append(line)
                elif line.startswith('-') and not line.startswith('---'):
                    result_lines.append(line)
                elif line.startswith('@@'):
                    result_lines.append(line)
                else:
                    result_lines.append(line)



            reversed_diff_type = {
                DiffType.MODIFIED: DiffType.MODIFIED,
                DiffType.NEW_FILE: DiffType.DELETED_FILE,
                DiffType.DELETED_FILE: DiffType.NEW_FILE
            }.get(diff.diff_type, diff.diff_type)
            
            
            header = f"Operation: {reversed_diff_type.name}, File: {diff.file}, Hunk: {diff.hunk_header}"
            limited_lines = result_lines[:100]
            content_str = "\n".join(limited_lines)
            return f"{header}\n{content_str}"
 

        return None


    def _group_continuous_blocks(self, content: List[str], sign: str):
        blocks = []
        start = None
        for i, line in enumerate(content):
            if line.startswith(sign):
                if start is None:
                    start = i
            else:
                if start is not None:
                    blocks.append((start, i - 1, content[start:i]))
                    start = None
        if start is not None:
            blocks.append((start, len(content) - 1, content[start:] ))
        return blocks
    
    
    def find_nearby_delete_blocks(self, diff, plus_idx):
        plus_blocks = self._group_continuous_blocks(diff.content, '+')
        del_blocks = self._group_continuous_blocks(diff.content, '-')
        lines = diff.content 

        def has_empty_line_between(start1, end2):
            for i in range(start1 + 1, end2):
                line = lines[i].strip()
                if line == '':
                    return True
            return False

        current_plus_block_idx = None
        for i, (start, end, _) in enumerate(plus_blocks):
            if start <= plus_idx <= end:
                current_plus_block_idx = i
                break

        prev_del_block = []
        next_del_block = []

        if current_plus_block_idx is not None:
            plus_start = plus_blocks[current_plus_block_idx][0]

            for b in reversed(del_blocks):
                if b[1] < plus_start and not has_empty_line_between(b[1], plus_start):
                    prev_del_block = b[2]
                    break

            for b in del_blocks:
                if b[0] > plus_start and not has_empty_line_between(plus_start, b[0]):
                    next_del_block = b[2]
                    break

        return prev_del_block, next_del_block

    

    def _score_semantic_similarity(self, diff, causes: List[str]) -> float:
        content_str = "\n".join(diff.content)
        relevant_score = sum(1 for cause in causes if cause in content_str)

        score = 0.0

        plus_blocks = self._group_continuous_blocks(diff.content, '+')  # [(start_idx, end_idx, block_lines)]
            
        for start, end, block_lines in plus_blocks:
            if not any(any(cause in line for cause in causes) for line in block_lines):
                continue

            plus_idx = start 
            prev_del_block, next_del_block = self.find_nearby_delete_blocks(diff, plus_idx)

            plus_block_str = "\n".join(line[1:].strip() for line in block_lines)
            prev_block_str = "\n".join(line[1:].strip() for line in prev_del_block)
            next_block_str = "\n".join(line[1:].strip() for line in next_del_block)
           

            similarity_prev = difflib.SequenceMatcher(None, prev_block_str, plus_block_str).ratio() if prev_block_str else 0
            similarity_next = difflib.SequenceMatcher(None, next_block_str, plus_block_str).ratio() if next_block_str else 0
            similarity = max(similarity_prev, similarity_next)


            
            if similarity > 0.9:
                score = 10
            elif similarity > 0.8 and score < 8:
                score = 8
            elif similarity > 0.7 and score < 6:
                score = 6
            elif similarity > 0.6 and score < 4:
                score = 4
            elif similarity > 0.5 and score < 2:
                score = 2
                
        return score
    

    def get_diff_brief_by_id(self, diff_id: int) -> Tuple[str, str, List[str]]:
        if 0 <= diff_id < len(self.diff_units):
            unit = self.diff_units[diff_id]
            preview = unit.content if isinstance(unit.content, list) else str(unit.content).splitlines()[:3]
            return unit.file, unit.hunk_header, preview
        return "<unknown>", "<none>", []

    
    def select_related_diff_pom(self, cause: List[str]) -> List[Tuple[int, float]]:
        scores = []
        for idx, diff in enumerate(self.diff_units):
            content_str = "\n".join(diff.content)
            tokens = set(re.findall(r"[\w\.\-]+", content_str)) 

            score = 0.0

            if diff.file.endswith('pom.xml'):
                score += 1.0
            
            for c in cause:
                if c in content_str:
                    score += 5.0

                for token in tokens:
                    if ratio(c, token) > 0.8:
                        score += 1
                    break

            scores.append((idx, score))

        top_scores = sorted(scores, key=lambda x: x[1], reverse=True)[:5]
        return top_scores
    

    def select_related_diff_assert(self, causes: List[str]) -> List[Tuple[int, float]]:
        scores = []
        for idx, diff in enumerate(self.diff_units):
            score = 0.0

            if diff.diff_type == DiffType.NEW_FILE:
                continue

            content_str = "\n".join(diff.content)
            for cause in causes:
                match = re.search(r"method\s+(\w+)\(", cause)                    
                pattern_def = rf"\b\w[\w\s<>,]*\s+{cause}\s*\("
                if re.search(pattern_def, content_str) and match == cause:
                    score += 10.0
                elif re.search(pattern_def, content_str):
                    score += 2.0
                elif cause in content_str:
                    score += 1.0

            if diff.file.endswith('.java'):
                score += self._score_semantic_similarity(diff, causes)
            else:
                score += self._score_semantic_similarity(diff, causes)/2
            
            scores.append((idx, score))
                

        scores.sort(key=lambda x: -x[1])
        return scores[:5] 


    def select_related_diff_test(self, group_key: str, causes: List[str]) -> List[Tuple[int, float]]:
        scores = []
        error_type = self.detect_error_type(group_key)
        
        for idx, diff in enumerate(self.diff_units):
            score = 0.0

            if diff.diff_type == DiffType.NEW_FILE:
                continue

            content_str = "\n".join(diff.content)


            for cause in causes:


                if error_type == "MissingPackage" or error_type == "MissingClass" or error_type == "TestFailure":
                    if diff.diff_type != DiffType.NEW_FILE and \
                        os.path.basename(diff.file) == f"{cause}.java" and \
                        ("package" in content_str or "parameters" in content_str):
                        score += 10.0
                    elif cause in content_str:
                        score += 1.0



                elif error_type == "MissingMethod": 
                    match = re.search(r"method\s+(\w+)\(", group_key)                    
                    pattern_def = rf"\b\w[\w\s<>,]*\s+{cause}\s*\("
                    if re.search(pattern_def, content_str) and match == cause:
                        score += 10.0
                    elif re.search(pattern_def, content_str):
                        score += 2.0
                    elif cause in content_str:
                        score += 1.0



                elif error_type == "TypeMismatch":
                    m = re.search(r"method\s+([A-Za-z_]\w*)\s*\(", group_key)
                    method_name = m.group(1) if m else None
                    cause_re = re.escape(cause)
                    sig_pattern = None
                    if method_name:
                        sig_pattern = re.compile(
                            rf"\b[\w<>\[\],\s]+\s+{re.escape(method_name)}\s*\([^)]*\)",
                            flags=re.MULTILINE
                        )
                    matched_in_sig = False
                    precise_match_found = False
                    if sig_pattern:
                        for sig_match in sig_pattern.finditer(content_str):
                            sig_text = sig_match.group(0)
                            matched_in_sig = True
                            if re.search(rf"\b{cause_re}\b", sig_text):
                                precise_match_found = True
                                break

                    generic_pattern = re.compile(rf"<[^>]*\b{cause_re}\b[^>]*>", flags=re.MULTILINE)
                    if not precise_match_found and generic_pattern.search(content_str):
                        precise_match_found = True
                    if precise_match_found:
                        score += 10.0
                    elif matched_in_sig:
                        score += 2.0
                    elif re.search(rf"\b{cause_re}\b", content_str):
                        score += 1.0

            if diff.file.endswith('.java'):
                score += self._score_semantic_similarity(diff, causes)
            else:
                score += self._score_semantic_similarity(diff, causes)/2
            
            scores.append((idx, score))
                

        scores.sort(key=lambda x: -x[1])
        return scores[:5] 



    def detect_error_type(self, group_key: str) -> str:
        if "package" in group_key and "does not exist" in group_key:
            return "MissingPackage"
        elif "cannot find symbol" in group_key and "class" in group_key:
            return "MissingClass"
        elif "cannot find symbol" in group_key and "method" in group_key:
            return "MissingMethod"
        elif "incompatible types" in group_key:
            return "TypeMismatch"
        elif "There are test failures." in group_key:
            return "TestFailure"
        else:
            return "Unknown"
