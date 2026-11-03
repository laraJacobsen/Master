// What the editor starts with for each question language. Judge0 runs Java as
// `java Main`, so a class with any other name can't start at all -- in the
// CodeNet eval that was the second most common Java crash (MainNotFound) --
// and a C main() that doesn't end with `return 0;` fails even when its output
// is right (NonZeroExit). The skeletons take both off the table. Python needs none.
const STARTERS: Record<string, string> = {
  java: ["public class Main {", "    public static void main(String[] args) {", "        ", "    }", "}", ""].join("\n"),
  c: ["#include <stdio.h>", "", "int main(void) {", "    ", "    return 0;", "}", ""].join("\n"),
};

export function starterCode(language: string): string {
  return STARTERS[language] ?? "";
}

// Code that's still just the starter (or empty) is nothing the student wrote:
// it isn't auto-submitted when time runs out.
export function isUntouched(code: string, language: string): boolean {
  return code.trim() === "" || code.trim() === starterCode(language).trim();
}
