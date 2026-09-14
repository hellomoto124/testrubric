import json
import re
from pathlib import Path


SOURCE = Path("/Users/xiexiaodong/mycuilaoshi/future_9量规体系_3.md")
OUTPUT = Path("backend/app/data/future_9.json")
SOURCE_URL = "https://www.redesignu.org/future9/"
IGNORED_HEADINGS = {"年级与等级对应关系", "九大素养领域概览"}


def clean(text: str) -> str:
    return re.sub(r"^[-*]\s*", "", text).strip()


def parse() -> dict:
    competencies = []
    current_competency = None
    current_skill = None
    current_level = None

    for raw_line in SOURCE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if match := re.fullmatch(r"##\s+(.+)", line):
            title = match.group(1)
            current_competency = None
            current_skill = None
            current_level = None
            if title not in IGNORED_HEADINGS:
                current_competency = {"name": title, "description": "", "skills": []}
                competencies.append(current_competency)
            continue
        if current_competency is None:
            continue
        if match := re.fullmatch(r"\*\*素养描述\*\*:(.+)", line):
            current_competency["description"] = match.group(1).strip()
        elif match := re.fullmatch(r"###\s+([A-Z]+\.\d+)\s+(.+)", line):
            current_skill = {
                "code": match.group(1),
                "name": match.group(2),
                "levels": [],
            }
            current_competency["skills"].append(current_skill)
            current_level = None
        elif current_skill and (
            match := re.fullmatch(r"\*\*Level\s+([1-6])\*\*.*", line)
        ):
            current_level = {"level": int(match.group(1)), "descriptors": []}
            current_skill["levels"].append(current_level)
        elif current_level and line.startswith("- "):
            current_level["descriptors"].append(clean(line))

    skills = [skill for competency in competencies for skill in competency["skills"]]
    assert len(competencies) == 9, len(competencies)
    assert len(skills) == 36, len(skills)
    assert all(
        [level["level"] for level in skill["levels"]] == [1, 2, 3, 4, 5, 6]
        for skill in skills
    )
    return {
        "rubric_version": "future-9-3",
        "source_url": SOURCE_URL,
        "license_note": "Future9 为开放资源；本地导入文本使用前仍须确认具体授权范围。",
        "local_adaptation": "不含年级映射，仅保留九项素养、三十六项技能及其六级描述。",
        "competencies": competencies,
    }


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(parse(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
