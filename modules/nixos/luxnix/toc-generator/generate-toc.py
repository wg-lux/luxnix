# scripts/generate-toc.py
import os
import re

def extract_headings(file_path):
    with open(file_path, 'r') as f:
        content = f.read()
    headings = re.findall(r'^#+\s+(.+)$', content, re.MULTILINE)
    return headings

def generate_toc():
    toc = ["# Table of Contents\n"]
    docs_dir = "docs"
    
    for file in sorted(os.listdir(docs_dir)):
        if file.endswith(".md"):
            file_path = os.path.join(docs_dir, file)
            headings = extract_headings(file_path)
            if headings:
                file_name = file[:-3]  # Remove .md
                toc.append(f"\n## [{file_name}](docs/{file})\n")
                for heading in headings:
                    anchor = heading.lower().replace(' ', '-')
                    toc.append(f"- [{heading}](docs/{file}#{anchor})")
    
    with open("TABLE_OF_CONTENTS.md", "w") as f:
        f.write("\n".join(toc))

if __name__ == "__main__":
    generate_toc()