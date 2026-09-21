# Real discussion-point Label sample -- human/expert spot-check

Generated 2026-09-21 against the live IDUN endpoint, current production pipeline (diff-against-reference clustering -> Label call). See generate_real_discussion_point_sample.py's module docstring for exactly which real data went in and why.

For each row: does the discussion point only state something true of every snippet shown (not a broader claim than the evidence supports), is it third-person/lecturer-facing (never "you"/"your"), and does it say something a lecturer could actually act on? Rate in the companion CSV -- leave the automated check out of this per pedagogical-feedback-design-decision.md decision 3.

## Row 1 -- sum-ints (5 students)

**Discussion point (generated):**
> All snippets add "+ 1" to the result of the VAR5(...) call (i.e., they end with ") + 1").

**Raw code snippets (deduplicated by student):**

```python
nums = input().split()
print(sum(int(n) for n in nums) + 1)
```

```python
nums = input().split()
print(sum(int(n) for n in nums) + 1)
```

```python
nums = input().split()
print(sum(int(n) for n in nums) + 1)
```

**Canonicalized snippets actually shown to the model:**

```
VAR1 = VAR2 ( ) . VAR3 ( ) VAR4 ( VAR5 ( VAR6 ( VAR7 ) for VAR7 in VAR1 ) + 1 )
```

```
VAR1 = VAR2 ( ) . VAR3 ( ) VAR4 ( VAR5 ( VAR6 ( VAR7 ) for VAR7 in VAR1 ) + 1 )
```

```
VAR1 = VAR2 ( ) . VAR3 ( ) VAR4 ( VAR5 ( VAR6 ( VAR7 ) for VAR7 in VAR1 ) + 1 )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 2 -- sum-ints (2 students)

**Discussion point (generated):**
> All snippets subtract 1 from the result of VAR5(...).

**Raw code snippets (deduplicated by student):**

```python
nums = input().split()
print(sum(int(n) for n in nums) - 1)
```

```python
nums = input().split()
print(sum(int(n) for n in nums) - 1)
```

**Canonicalized snippets actually shown to the model:**

```
VAR1 = VAR2 ( ) . VAR3 ( ) VAR4 ( VAR5 ( VAR6 ( VAR7 ) for VAR7 in VAR1 ) - 1 )
```

```
VAR1 = VAR2 ( ) . VAR3 ( ) VAR4 ( VAR5 ( VAR6 ( VAR7 ) for VAR7 in VAR1 ) - 1 )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 3 -- sum-ints (4 students)

**Discussion point (generated):**
> All snippets apply a slice to VAR1 within a generator expression passed to VAR5.

**Raw code snippets (deduplicated by student):**

```python
nums = input().split()
print(sum(int(n) for n in nums[1:]))
```

```python
nums = input().split()
print(sum(int(n) for n in nums[:-1]))
```

```python
nums = input().split()
print(sum(int(n) for n in nums[:-1]))
```

**Canonicalized snippets actually shown to the model:**

```
VAR1 = VAR2 ( ) . VAR3 ( ) VAR4 ( VAR5 ( VAR6 ( VAR7 ) for VAR7 in VAR1 [ 1 : ] ) )
```

```
VAR1 = VAR2 ( ) . VAR3 ( ) VAR4 ( VAR5 ( VAR6 ( VAR7 ) for VAR7 in VAR1 [ : - 1 ] ) )
```

```
VAR1 = VAR2 ( ) . VAR3 ( ) VAR4 ( VAR5 ( VAR6 ( VAR7 ) for VAR7 in VAR1 [ : - 1 ] ) )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 4 -- sum-ints (2 students)

**Discussion point (generated):**
> The students' snippets both contain a space instead of a dot between the call to VAR3() and the subsequent call to VAR4(...).

**Raw code snippets (deduplicated by student):**

```python
nums = input().split()
print(int(nums[0]))
```

```python
nums = input().split()
print(int(nums[0]))
```

**Canonicalized snippets actually shown to the model:**

```
VAR1 = VAR2 ( ) . VAR3 ( ) VAR4 ( VAR5 ( VAR1 [ 0 ] ) )
```

```
VAR1 = VAR2 ( ) . VAR3 ( ) VAR4 ( VAR5 ( VAR1 [ 0 ] ) )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 5 -- sum-ints (2 students)

**Discussion point (generated):**
> Both snippets contain a for-loop that updates VAR4 with the '*=' operator using the result of VAR6(VAR5).

**Raw code snippets (deduplicated by student):**

```python
nums = input().split()
result = 1
for n in nums:
    result *= int(n)
print(result)
```

```python
nums = input().split()
result = 1
for n in nums:
    result *= int(n)
print(result)
```

**Canonicalized snippets actually shown to the model:**

```
VAR1 = VAR2 ( ) . VAR3 ( ) VAR4 = 1 for VAR5 in VAR1 : VAR4 *= VAR6 ( VAR5 ) VAR7 ( VAR4 )
```

```
VAR1 = VAR2 ( ) . VAR3 ( ) VAR4 = 1 for VAR5 in VAR1 : VAR4 *= VAR6 ( VAR5 ) VAR7 ( VAR4 )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 6 -- double-it (2 students)

**Discussion point (generated):**
> Both snippets add a literal +2 to the result of VAR2(VAR3()) within the call to VAR1.

**Raw code snippets (deduplicated by student):**

```python
print(int(input()) + 2)
```

```python
print(int(input()) + 2)
```

**Canonicalized snippets actually shown to the model:**

```
VAR1 ( VAR2 ( VAR3 ( ) ) + 2 )
```

```
VAR1 ( VAR2 ( VAR3 ( ) ) + 2 )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 7 -- double-it (2 students)

**Discussion point (generated):**
> Both snippets place two function calls sequentially on the same line, separated only by a space and no operator or delimiter.

**Raw code snippets (deduplicated by student):**

```python
int = input()
print(int*2)
```

```python
int = input()
print(int*2)
```

**Canonicalized snippets actually shown to the model:**

```
VAR1 = VAR2 ( ) VAR3 ( VAR1 * 2 )
```

```
VAR1 = VAR2 ( ) VAR3 ( VAR1 * 2 )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 8 -- is_palindrome (2 students)

**Discussion point (generated):**
> Both snippets include a return statement that compares a variable to its slice with a negative step (e.g., VAR3 == VAR3[:: -1]).

**Raw code snippets (deduplicated by student):**

```python
def is_palindrome(s):
    t = s.replace(" ", "")  # forgot to lowercase
    return t == t[::-1]

s = input()
print(is_palindrome(s))

```

```python
def is_palindrome(s):
    t = s.replace(" ", "")  # forgot to lowercase
    return t == t[::-1]

s = input()
print(is_palindrome(s))

```

**Canonicalized snippets actually shown to the model:**

```
def VAR1 ( VAR2 ) : VAR3 = VAR2 . VAR4 ( " " , "" ) return VAR3 == VAR3 [ : : - 1 ] VAR2 = VAR5 ( ) VAR6 ( VAR1 ( VAR2 ) )
```

```
def VAR1 ( VAR2 ) : VAR3 = VAR2 . VAR4 ( " " , "" ) return VAR3 == VAR3 [ : : - 1 ] VAR2 = VAR5 ( ) VAR6 ( VAR1 ( VAR2 ) )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 9 -- is_palindrome (2 students)

**Discussion point (generated):**
> All snippets contain a return statement that compares a variable to its slice with a step of -1 (e.g., VAR3 == VAR3[:: -1]).

**Raw code snippets (deduplicated by student):**

```python
def is_palindrome(s):
    t = s.lower()  # forgot to strip spaces
    return t == t[::-1]

s = input()
print(is_palindrome(s))

```

```python
def is_palindrome(s):
    t = s.lower()  # forgot to strip spaces
    return t == t[::-1]

s = input()
print(is_palindrome(s))

```

**Canonicalized snippets actually shown to the model:**

```
def VAR1 ( VAR2 ) : VAR3 = VAR2 . VAR4 ( ) return VAR3 == VAR3 [ : : - 1 ] VAR2 = VAR5 ( ) VAR6 ( VAR1 ( VAR2 ) )
```

```
def VAR1 ( VAR2 ) : VAR3 = VAR2 . VAR4 ( ) return VAR3 == VAR3 [ : : - 1 ] VAR2 = VAR5 ( ) VAR6 ( VAR1 ( VAR2 ) )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 10 -- is_palindrome (2 students)

**Discussion point (generated):**
> Both snippets iterate over VAR9(VAR6 // 2) and compare VAR3[VAR8] with VAR3[VAR6 - VAR8 - 2] inside the loop.

**Raw code snippets (deduplicated by student):**

```python
def is_palindrome(s):
    t = s.lower().replace(" ", "")
    n = len(t)
    for i in range(n // 2):
        if t[i] != t[n - i - 2]:  # off-by-one: should be n - i - 1
            return False
    return True

s = input()
print(is_palindrome(s))

```

```python
def is_palindrome(s):
    t = s.lower().replace(" ", "")
    n = len(t)
    for i in range(n // 2):
        if t[i] != t[n - i - 2]:  # off-by-one: should be n - i - 1
            return False
    return True

s = input()
print(is_palindrome(s))

```

**Canonicalized snippets actually shown to the model:**

```
def VAR1 ( VAR2 ) : VAR3 = VAR2 . VAR4 ( ) . VAR5 ( " " , "" ) VAR6 = VAR7 ( VAR3 ) for VAR8 in VAR9 ( VAR6 // 2 ) : if VAR3 [ VAR8 ] != VAR3 [ VAR6 - VAR8 - 2 ] : return False return True VAR2 = VAR10 ( ) VAR11 ( VAR1 ( VAR2 ) )
```

```
def VAR1 ( VAR2 ) : VAR3 = VAR2 . VAR4 ( ) . VAR5 ( " " , "" ) VAR6 = VAR7 ( VAR3 ) for VAR8 in VAR9 ( VAR6 // 2 ) : if VAR3 [ VAR8 ] != VAR3 [ VAR6 - VAR8 - 2 ] : return False return True VAR2 = VAR10 ( ) VAR11 ( VAR1 ( VAR2 ) )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 11 -- count_vowels (2 students)

**Discussion point (generated):**
> Both snippets contain a for-loop iterating over VAR2 with an if-statement checking whether the loop variable is in the string "aeiou".

**Raw code snippets (deduplicated by student):**

```python
def count_vowels(s):
    vowels = "aeiou"  # forgot to lowercase s first
    count = 0
    for ch in s:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))

```

```python
def count_vowels(s):
    vowels = "aeiou"  # forgot to lowercase s first
    count = 0
    for ch in s:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))

```

**Canonicalized snippets actually shown to the model:**

```
def VAR1 ( VAR2 ) : VAR3 = "aeiou" VAR4 = 0 for VAR5 in VAR2 : if VAR5 in VAR3 : VAR4 += 1 return VAR4 VAR2 = VAR6 ( ) VAR7 ( VAR1 ( VAR2 ) )
```

```
def VAR1 ( VAR2 ) : VAR3 = "aeiou" VAR4 = 0 for VAR5 in VAR2 : if VAR5 in VAR3 : VAR4 += 1 return VAR4 VAR2 = VAR6 ( ) VAR7 ( VAR1 ( VAR2 ) )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 12 -- count_vowels (2 students)

**Discussion point (generated):**
> Both snippets contain a for loop that iterates over VAR3 and increments VAR6 whenever an element is found in the string VAR5 ('aeiouy').

**Raw code snippets (deduplicated by student):**

```python
def count_vowels(s):
    t = s.lower()
    vowels = "aeiouy"  # bug: y isn't a vowel
    count = 0
    for ch in t:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))

```

```python
def count_vowels(s):
    t = s.lower()
    vowels = "aeiouy"  # bug: y isn't a vowel
    count = 0
    for ch in t:
        if ch in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))

```

**Canonicalized snippets actually shown to the model:**

```
def VAR1 ( VAR2 ) : VAR3 = VAR2 . VAR4 ( ) VAR5 = "aeiouy" VAR6 = 0 for VAR7 in VAR3 : if VAR7 in VAR5 : VAR6 += 1 return VAR6 VAR2 = VAR8 ( ) VAR9 ( VAR1 ( VAR2 ) )
```

```
def VAR1 ( VAR2 ) : VAR3 = VAR2 . VAR4 ( ) VAR5 = "aeiouy" VAR6 = 0 for VAR7 in VAR3 : if VAR7 in VAR5 : VAR6 += 1 return VAR6 VAR2 = VAR8 ( ) VAR9 ( VAR1 ( VAR2 ) )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 13 -- count_vowels (2 students)

**Discussion point (generated):**
> All snippets contain a for loop that iterates over VAR8(VAR9(VAR3) - 1).

**Raw code snippets (deduplicated by student):**

```python
def count_vowels(s):
    t = s.lower()
    vowels = "aeiou"
    count = 0
    for i in range(len(t) - 1):  # off-by-one: skips the last character
        if t[i] in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))

```

```python
def count_vowels(s):
    t = s.lower()
    vowels = "aeiou"
    count = 0
    for i in range(len(t) - 1):  # off-by-one: skips the last character
        if t[i] in vowels:
            count += 1
    return count

s = input()
print(count_vowels(s))

```

**Canonicalized snippets actually shown to the model:**

```
def VAR1 ( VAR2 ) : VAR3 = VAR2 . VAR4 ( ) VAR5 = "aeiou" VAR6 = 0 for VAR7 in VAR8 ( VAR9 ( VAR3 ) - 1 ) : if VAR3 [ VAR7 ] in VAR5 : VAR6 += 1 return VAR6 VAR2 = VAR10 ( ) VAR11 ( VAR1 ( VAR2 ) )
```

```
def VAR1 ( VAR2 ) : VAR3 = VAR2 . VAR4 ( ) VAR5 = "aeiou" VAR6 = 0 for VAR7 in VAR8 ( VAR9 ( VAR3 ) - 1 ) : if VAR3 [ VAR7 ] in VAR5 : VAR6 += 1 return VAR6 VAR2 = VAR10 ( ) VAR11 ( VAR1 ( VAR2 ) )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 14 -- second_largest (2 students)

**Discussion point (generated):**
> Each snippet calls VAR4 with the keyword argument VAR5 set to True.

**Raw code snippets (deduplicated by student):**

```python
def second_largest(nums):
    s = sorted(nums, reverse=True)  # no dedup: picks second position, not second distinct value
    return s[1]

nums = [int(x) for x in input().split()]
print(second_largest(nums))

```

```python
def second_largest(nums):
    s = sorted(nums, reverse=True)  # no dedup: picks second position, not second distinct value
    return s[1]

nums = [int(x) for x in input().split()]
print(second_largest(nums))

```

**Canonicalized snippets actually shown to the model:**

```
def VAR1 ( VAR2 ) : VAR3 = VAR4 ( VAR2 , VAR5 = True ) return VAR3 [ 1 ] VAR2 = [ VAR6 ( VAR7 ) for VAR7 in VAR8 ( ) . VAR9 ( ) ] VAR10 ( VAR1 ( VAR2 ) )
```

```
def VAR1 ( VAR2 ) : VAR3 = VAR4 ( VAR2 , VAR5 = True ) return VAR3 [ 1 ] VAR2 = [ VAR6 ( VAR7 ) for VAR7 in VAR8 ( ) . VAR9 ( ) ] VAR10 ( VAR1 ( VAR2 ) )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 15 -- second_largest (2 students)

**Discussion point (generated):**
> The students' snippets both return the element at index 1 of VAR3.

**Raw code snippets (deduplicated by student):**

```python
def second_largest(nums):
    s = sorted(set(nums))  # ascending, not descending
    return s[1]  # grabs second-smallest distinct instead of second-largest

nums = [int(x) for x in input().split()]
print(second_largest(nums))

```

```python
def second_largest(nums):
    s = sorted(set(nums))  # ascending, not descending
    return s[1]  # grabs second-smallest distinct instead of second-largest

nums = [int(x) for x in input().split()]
print(second_largest(nums))

```

**Canonicalized snippets actually shown to the model:**

```
def VAR1 ( VAR2 ) : VAR3 = VAR4 ( VAR5 ( VAR2 ) ) return VAR3 [ 1 ] VAR2 = [ VAR6 ( VAR7 ) for VAR7 in VAR8 ( ) . VAR9 ( ) ] VAR10 ( VAR1 ( VAR2 ) )
```

```
def VAR1 ( VAR2 ) : VAR3 = VAR4 ( VAR5 ( VAR2 ) ) return VAR3 [ 1 ] VAR2 = [ VAR6 ( VAR7 ) for VAR7 in VAR8 ( ) . VAR9 ( ) ] VAR10 ( VAR1 ( VAR2 ) )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______

## Row 16 -- second_largest (2 students)

**Discussion point (generated):**
> Both snippets initialize VAR5 to None before iterating over VAR2 in a for‑loop.

**Raw code snippets (deduplicated by student):**

```python
def second_largest(nums):
    largest = max(nums)
    second = None
    for n in nums:
        if n != largest:
            if second is None or n < second:  # bug: should be n > second
                second = n
    return second

nums = [int(x) for x in input().split()]
print(second_largest(nums))

```

```python
def second_largest(nums):
    largest = max(nums)
    second = None
    for n in nums:
        if n != largest:
            if second is None or n < second:  # bug: should be n > second
                second = n
    return second

nums = [int(x) for x in input().split()]
print(second_largest(nums))

```

**Canonicalized snippets actually shown to the model:**

```
def VAR1 ( VAR2 ) : VAR3 = VAR4 ( VAR2 ) VAR5 = None for VAR6 in VAR2 : if VAR6 != VAR3 : if VAR5 is None or VAR6 < VAR5 : VAR5 = VAR6 return VAR5 VAR2 = [ VAR7 ( VAR8 ) for VAR8 in VAR9 ( ) . VAR10 ( ) ] VAR11 ( VAR1 ( VAR2 ) )
```

```
def VAR1 ( VAR2 ) : VAR3 = VAR4 ( VAR2 ) VAR5 = None for VAR6 in VAR2 : if VAR6 != VAR3 : if VAR5 is None or VAR6 < VAR5 : VAR5 = VAR6 return VAR5 VAR2 = [ VAR7 ( VAR8 ) for VAR8 in VAR9 ( ) . VAR10 ( ) ] VAR11 ( VAR1 ( VAR2 ) )
```

- is_grounded_y_n: ______
- is_lecturer_facing_y_n: ______
- is_actionable_y_n: ______
