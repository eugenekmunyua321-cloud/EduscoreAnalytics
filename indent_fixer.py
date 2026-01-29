import re

with open(r'c:\Users\user\Desktop\Analysis App\Exam1\pages\saved_exams.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Lines within the expander block need adjustment
# After "if order_list_source ==", the next lines should be indented properly

i = 0
while i < len(lines):
    line = lines[i]
    stripped = line.lstrip()
    current_indent = len(line) - len(stripped)
    
    # Find lines that should be indented more (immediately after if/else/for/while/with/etc)
    if stripped.startswith(('if ', 'elif ', 'else:', 'for ', 'while ', 'with ', 'try:', 'except', 'finally:', 'def ', 'class ')):
        # Next non-empty line should have at least current_indent + 4
        j = i + 1
        while j < len(lines):
            next_line = lines[j]
            next_stripped = next_line.lstrip()
            if next_stripped:  # Non-empty line
                next_indent = len(next_line) - len(next_stripped)
                # If next line doesn't have enough indentation
                if next_indent <= current_indent:
                    lines[j] = '    ' + next_line
                break
            j += 1
    
    i += 1

with open(r'c:\Users\user\Desktop\Analysis App\Exam1\pages\saved_exams.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Fixed nested indentation')
