// What a student's editor starts with. A lecturer can write their own starter
// per task on the setup page (questions.starter_code -- helper functions, a
// skeleton to complete); when they haven't, it's the built-in default below.
// Both the setup page (to show and pre-fill the default) and the student page
// use this file, so they can't disagree about what "default" means.
//
// The built-in default for each question language: Judge0 runs Java as
// `java Main`, so a class with any other name can't start at all -- in the
// CodeNet eval that was the second most common Java crash (MainNotFound) --
// and a C main() that doesn't end with `return 0;` fails even when its output
// is right (NonZeroExit). The skeletons take both off the table. Python needs none.
const STARTERS: Record<string, string> = {
  java: ["public class Main {", "    public static void main(String[] args) {", "        ", "    }", "}", ""].join("\n"),
  c: ["#include <stdio.h>", "", "int main(void) {", "    ", "    return 0;", "}", ""].join("\n"),
};

// Tasks whose data is in a file (and that give nothing on standard input)
// start with standard input pointed at that file, so students read it exactly
// like typed input -- input() / scanf / Scanner -- instead of first having to
// learn file handling. The backend doesn't count the redirect line itself as
// "reading the input" (validation.reads_input), so hard-coded answers are
// still caught.
function fileStarter(language: string, file: string): string | null {
  const name = JSON.stringify(file);
  switch (language) {
    case "python":
      return [
        "import sys",
        "",
        `# input() now reads ${file}, one line per call, as if it were typed in.`,
        `sys.stdin = open(${name})`,
        "",
        "",
      ].join("\n");
    case "c":
      return [
        "#include <stdio.h>",
        "",
        "int main(void) {",
        `    /* scanf now reads ${file}, as if it were typed in. */`,
        `    freopen(${name}, "r", stdin);`,
        "    ",
        "    return 0;",
        "}",
        "",
      ].join("\n");
    case "java":
      return [
        "import java.io.FileInputStream;",
        "import java.util.Scanner;",
        "",
        "public class Main {",
        "    public static void main(String[] args) throws Exception {",
        `        // System.in now reads ${file}, as if it were typed in.`,
        `        System.setIn(new FileInputStream(${name}));`,
        "        Scanner in = new Scanner(System.in);",
        "        ",
        "    }",
        "}",
        "",
      ].join("\n");
    default:
      return null;
  }
}

export interface StarterExample {
  /** The example test's standard input. */
  stdin: string;
  /** Names of the example test's data files, in order. */
  files: string[];
}

/** The built-in starter for a task: the language's skeleton, with standard
 *  input pointed at the example's first data file when the task gives nothing
 *  on standard input itself. */
export function defaultStarterCode(language: string, example: StarterExample | null = null): string {
  const inputFile = example && !example.stdin.trim() ? (example.files[0] ?? null) : null;
  if (inputFile) {
    const s = fileStarter(language, inputFile);
    if (s) return s;
  }
  return STARTERS[language] ?? "";
}

// Code that's still just the starter (or empty) is nothing the student wrote:
// it isn't auto-submitted when time runs out.
export function isUntouched(code: string, starter: string): boolean {
  return code.trim() === "" || code.trim() === starter.trim();
}
