import sys

extension = open('stage2/solvers/extension.py').read()
for path in ['stage2/solvers/gemma_4_31b/solver.py', 'stage2/solvers/gpt_oss_120b/solver.py']:
    with open(path, 'r', encoding='utf-8') as f:
        code = f.read()
    code = code.replace('def main():', 'def original_main():')
    code = code.replace('if __name__ == "__main__":\n    main()', 'if __name__ == "__main__":\n    ultimate_main()')
    code = code.replace('if __name__ == \'__main__\':\n    main()', 'if __name__ == \'__main__\':\n    ultimate_main()')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(extension + '\n\n' + code)
print('Injection successful')
