"""
Fix indentation for the three main view blocks:
- if st.session_state.view == "preview": (line ~622)
- elif st.session_state.view == "analysis": (line ~772)
- else: (line ~1429) for main view
"""

with open("app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find the three blocks
preview_line = None
analysis_line = None
else_line = None

for i, line in enumerate(lines):
    if 'if st.session_state.view == "preview":' in line and preview_line is None:
        preview_line = i
    elif 'elif st.session_state.view == "analysis":' in line and analysis_line is None:
        analysis_line = i
    elif line.strip().startswith("else:") and i > 1400 and else_line is None:
        # The main else block near end of file
        else_line = i

print(f"Found: preview={preview_line}, analysis={analysis_line}, else={else_line}")

# Now fix indentation: all lines between preview_line+1 and analysis_line should be indented by 4
# all lines between analysis_line+1 and else_line should be indented by 4
# all lines between else_line+1 and end should be indented by 4

fixed_lines = []

for i, line in enumerate(lines):
    if i <= preview_line:
        # Before preview block
        fixed_lines.append(line)
    elif preview_line < i < analysis_line:
        # Inside preview block - ensure minimum 4 space indent
        if line.strip():  # Not empty
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)
            if current_indent < 4:
                fixed_lines.append('    ' + stripped)
            else:
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)
    elif i == analysis_line:
        # The elif line itself
        fixed_lines.append(line)
    elif analysis_line < i < else_line:
        # Inside analysis block
        if line.strip():
            stripped = line.lstrip()
            current_indent = len(line) - len(stripped)
            if current_indent < 4:
                fixed_lines.append('    ' + stripped)
            else:
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)
    elif i == else_line:
        # The else line
        fixed_lines.append(line)
    elif i > else_line:
        # Inside else block
        if line.strip():
            stripped = line.lstrip()
            # Check if this is the footer section (should not be indented)
            if "# Footer" in line or "# ---" in line and i > 1600:
                fixed_lines.append(line)
            else:
                current_indent = len(line) - len(stripped)
                if current_indent < 4:
                    fixed_lines.append('    ' + stripped)
                else:
                    fixed_lines.append(line)
        else:
            fixed_lines.append(line)

with open("app.py", "w", encoding="utf-8") as f:
    f.writelines(fixed_lines)

print(f"✓ Fixed all three view blocks!")
