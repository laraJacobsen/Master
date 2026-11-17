# Headline sample -- human/expert spot-check (round 1)

Generated 2026-11-17 against the live endpoint (provider `idun`, model `openai/gpt-oss-120b`). 28 rows, one per curated (hand-written) discussion line in feedback.py. Headlines for AI-written notes are rated in Label round 6. {failed} call(s) failed and fell back to showing the note as the headline (marked below; nothing to rate).

The model saw only the category and the note -- never code. For each row:

- **is_faithful_to_note**: do the title and action say only what the note says? (No new cause, code detail, example or claim.)
- **title_names_mistake**: does the title name the actual mistake, not just repeat the category?
- **is_lecturer_facing**: addressed to the lecturer, never the students?
- **is_actionable**: is the action something a lecturer could do in class right now?

Rate in the companion CSV. Leave its automatic-flag columns until after rating.

**Pass rule (write this before rating, don't change it after):**

> 

## Row 1 -- Runtime error (NameError)

**Note the model was given:**
> NameError. Check the traceback's last line for the name it flags: a typo, or a name never defined.

**Title:** Undefined name runtime error

**Action:** Show the traceback and highlight the last line where the undefined name appears

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 2 -- Runtime error (AttributeError)

**Note the model was given:**
> AttributeError: check the exact method name against the real API. Likely a small misspelling.

**Title:** Incorrect method name

**Action:** Show the official API documentation and ask the class to compare the method name they used.

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 3 -- Runtime error (RecursionError)

**Note the model was given:**
> RecursionError: check whether the function has a base case that stops the recursion.

**Title:** Missing base case in recursion

**Action:** Show how to add a base case to stop the recursion

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 4 -- Runtime error (TypeError)

**Note the model was given:**
> TypeError: check the types or argument count on the flagged line against what's expected.

**Title:** Incorrect argument types

**Action:** Show the flagged line and discuss the expected types and argument count

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 5 -- Runtime error (IndexError)

**Note the model was given:**
> IndexError: check the index against the sequence's actual valid range.

**Title:** Index out of range error

**Action:** Show the sequence length and ask students to verify the index is within the valid range.

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 6 -- Runtime error (KeyError)

**Note the model was given:**
> KeyError: check whether the key was added to the dictionary before it's looked up.

**Title:** Missing dictionary key

**Action:** Show the class how to check if a key exists before accessing it

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 7 -- Runtime error (ModuleNotFoundError)

**Note the model was given:**
> ModuleNotFoundError: check whether the exercise actually needs that import.

**Title:** Missing module import

**Action:** Ask the class if the exercise actually needs that import

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 8 -- Runtime error (EOFError)

**Note the model was given:**
> EOFError: check whether the code is reading more input than it's actually given.

**Title:** Attempted to read beyond input

**Action:** Show the class how to count input statements and ensure they match the available input data.

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 9 -- Runtime error (SegmentationFault)

**Note the model was given:**
> Segmentation fault: check scanf for a missing &, array indexes, printf given '#' instead of "#", and oversized arrays.

**Title:** Segmentation fault in input handling

**Action:** Show the class how to check scanf for a missing &, verify array indexes, correct printf strings, and avoid oversized arrays

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 10 -- Runtime error (FloatingPointException)

**Note the model was given:**
> Integer division or % by zero. Check which divisor can be 0 for the test input.

**Title:** Division by zero error

**Action:** Show the test input and ask the class to locate any divisor that could be zero.

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 11 -- Runtime error (Aborted)

**Note the model was given:**
> Aborted, usually a failed assert(). Worth reading which assertion failed.

**Title:** Program aborted due to assert

**Action:** Show the assertion failure message and discuss why it was triggered.

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 12 -- Runtime error (NonZeroExit)

**Note the model was given:**
> main didn't return 0. Worth a reminder to declare int main and end it with return 0;

**Title:** Missing return value in main

**Action:** Remind the class to declare int main and end it with return 0

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 13 -- Runtime error (MainNotFound)

**Note the model was given:**
> Couldn't start: the class must be named Main, with no package line.

**Title:** Missing Main class

**Action:** Show that the class must be named Main and have no package line

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 14 -- Runtime error (NoSuchElementException)

**Note the model was given:**
> NoSuchElementException: the code reads more input than it's given.

**Title:** Attempting to read beyond input

**Action:** Show the input‑reading code and discuss why it may exceed the supplied data.

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 15 -- Runtime error (InputMismatchException)

**Note the model was given:**
> InputMismatchException: the Scanner method doesn't match the input's type.

**Title:** Scanner input type mismatch

**Action:** Show the class how the Scanner method expects a matching input type and ask them to check the input format.

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 16 -- Runtime error (NumberFormatException)

**Note the model was given:**
> NumberFormatException: often parseInt on a whole line that holds several numbers, or on readLine()'s null after the input ran out.

**Title:** Parsing whole line as integer

**Action:** Show the class how to split the input line into individual numbers before using parseInt

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 17 -- Runtime error (NullPointerException)

**Note the model was given:**
> NullPointerException: a variable used before it's given an object, often readLine()'s null after the input ran out.

**Title:** Variable used before object assigned

**Action:** Show the stack trace and ask why the variable is null after input ends.

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 18 -- Runtime error (ArithmeticException)

**Note the model was given:**
> ArithmeticException, usually integer division by zero.

**Title:** Integer division by zero

**Action:** Show the stack trace and ask why dividing by zero triggered the ArithmeticException

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 19 -- Runtime error (ArrayIndexOutOfBoundsException)

**Note the model was given:**
> ArrayIndexOutOfBoundsException: check the index against the length, often <= instead of <.

**Title:** Array index out of bounds

**Action:** Show the class how to check the index against the array length using < instead of <=.

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 20 -- Runtime error (ValueError)

**Note the model was given:**
> ValueError. Worth reading through the error output together to see exactly where it crashed.

**Title:** Runtime value error

**Action:** Show the error output and walk through where it crashed

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 21 -- Wrong answer

**Note the model was given:**
> Wrong answer. Worth tracing through the test input step by step to see where the logic diverges.

**Title:** Incorrect output produced

**Action:** Trace the test input step by step to locate the logic divergence

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 22 -- Syntax error

**Note the model was given:**
> Syntax error. Worth comparing the flagged line against the exact pattern from the lecture slides.

**Title:** Line does not match syntax pattern

**Action:** Show the flagged line and compare it to the exact pattern from the lecture slides

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 23 -- Compile error

**Note the model was given:**
> Compile error. Worth reading the compiler's first error together: the ones after it often follow from it.

**Title:** First compile error

**Action:** Show the compiler's first error and discuss it with the class.

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 24 -- Function not found

**Note the model was given:**
> Function not found. Worth double-checking the exact function name the exercise asks for.

**Title:** Missing expected function

**Action:** Verify the exact function name the exercise requests.

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 25 -- Timeout

**Note the model was given:**
> Didn't finish. Worth checking what should update the loop's stopping condition.

**Title:** Loop condition never updates

**Action:** Show the loop’s stopping condition on the board and discuss how it should be updated.

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 26 -- Oom

**Note the model was given:**
> Didn't finish. Worth checking what should update the loop's stopping condition.

**Title:** Loop never updates stop condition

**Action:** Trace the loop and highlight that the stopping condition is never updated

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 27 -- Output limit exceeded

**Note the model was given:**
> Didn't finish. Worth checking what should update the loop's stopping condition.

**Title:** Loop stopped too early

**Action:** Show the loop's stopping condition and discuss how to adjust it.

- is_faithful_to_note_y_n:n
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y

## Row 28 -- Rejected

**Note the model was given:**
> Rejected submissions. Worth a reminder on what counts as a valid submission.

**Title:** Invalid submission format

**Action:** Remind the class what counts as a valid submission.

- is_faithful_to_note_y_n:y
- title_names_mistake_y_n:y
- is_lecturer_facing_y_n:y
- is_actionable_y_n:y
