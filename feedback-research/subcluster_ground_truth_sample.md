# Wrong-answer sub-clustering: ground truth labeling sample

For each exercise below, fill in `bug_group` in the companion CSV (`subcluster_ground_truth_sample.csv`) for every submission id: submissions that share the same underlying bug get the same group label (e.g. `off-by-one`, `missing-lower`, `g1`, whatever's convenient) within that exercise. Group labels only need to be consistent within an exercise, not across exercises.

## sum-ints

### SI-01

```python
nums = input().split()
print(sum(int(n) for n in nums[:-1]))
```

bug_group: missing-last-element  

### SI-02

```python
nums = input().split()
result = 1
for n in nums:
    result *= int(n)
print(result)
```

bug_group:  multiply

### SI-03

```python
nums = input().split()
print(sum(int(n) for n in nums[1:]))
```

bug_group:  missing-first-element

### SI-04

```python
nums = input().split()
print(sum(int(n) for n in nums) - 1)
```

bug_group:  one-less

### SI-05

```python
nums = input().split()
result = 1
for n in nums:
    result *= int(n)
print(result)
```

bug_group:  multiply

### SI-06

```python
nums = input().split()
print(int(nums[0]))
```

bug_group:  first-num-only

### SI-07

```python
nums = input().split()
print(sum(int(n) for n in nums) - 1)
```

bug_group:  one-less

### SI-08

```python
nums = input().split()
print(sum(int(n) for n in nums) + 1)
```

bug_group: one-more 

### SI-09

```python
nums = input().split()
print(sum(int(n) for n in nums[:-1]))
```

bug_group: missing-last-element

### SI-10

```python
nums = input().split()
print(sum(int(n) for n in nums) + 1)
```

bug_group: one-more

### SI-11

```python
nums = input().split()
print(sum(int(n) for n in nums) + 1)
```

bug_group: one-more

### SI-12

```python
nums = input().split()
print(int(nums[0]))
```

bug_group: first-num-only

### SI-13

```python
nums = input().split()
print(sum(int(n) for n in nums) + 1)
```

bug_group: one-more

### SI-14

```python
nums = input().split()
print(sum(int(n) for n in nums) + 1)
```

bug_group: one-more

### SI-15

```python
nums = input().split()
print(sum(int(n) for n in nums[:-1]))
```

bug_group: missing-last-element

## double-it

### DI-01

```python
int = input()
print(int*2)
```

bug_group: prints-twice

### DI-02

```python
int = input()
print(int*2)
```

bug_group: prints-twice

### DI-03

```python
print(int(input()) + 2)
```

bug_group: adds-two

### DI-04

```python
print(int(input()) + 2)
```

bug_group: adds-two

### DI-05

```python
print(input()*2)
```

bug_group: prints-twice

### DI-06

```python
print(int(input()) + 2)
```

bug_group: adds-two

### DI-07

```python
print(int(input()*2))
```

bug_group: ______

### DI-08

```python
print(int(input()) + 2)
```

bug_group: adds-two

### DI-09

```python
print(int(input()) + 2)
```

bug_group: adds-two

### DI-10

```python
print(int(input()) + 2)
```

bug_group: adds-two

### DI-11

```python
n = int(input())
print(n + n + 1)
```

bug_group: one-more

## is_palindrome

### PAL-01

```python
def is_palindrome(s):
    t = s.replace(" ", "")  # forgot to lowercase
    return t == t[::-1]

s = input()
print(is_palindrome(s))

```

bug_group: missing-lowercase

### PAL-02

```python
def is_palindrome(s):
    t = s.lower()  # forgot to strip spaces
    return t == t[::-1]

s = input()
print(is_palindrome(s))

```

bug_group: forgot-strip

### PAL-03

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

bug_group: off-by-one
