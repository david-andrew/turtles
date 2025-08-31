# basically a minimal scheme/lisp style parser


"""
Token types:
- parenthesis
- delimited strings
- non-delimited strings
- reserved words (potentially just assigned delimited strings...)

- tbd about other atom token types. proabably also have integer


syntax goals:
- fn declaration
    (fn (<args>) (<expression>))
    (fn (x y) (+ x y))
- variable assignment
    (= name value)
    (= x 10)
    (= add5 (fn x (+ x 5)))
    (= mylist (1 2 3 4 5))
    (= mystr 'something')

(maybe)
- simple partial eval. could basically treat all functions like functional curried functions. so can apply values in the declaration sequence (but can't go out of order)
    (= add (fn (x y) (+ x y)))
    (= add5 (add 5))
- variable arg functions?
    (+ 1 2 3 4 5)
    probably need special syntax to handle it, e.g.
    (= fn= (fn (name ... expr) (= [name] (fn (...) expr))))  // seems like a pain in the butt lol



[functions to add]
- string interpolator
(= apple 1)
(= banana 2)
(= peach 3)
(= pear 4)
(= pineapple 5)
(join 'a ' apple ' string ' banana ' with ' 42 ' lots ' peach ' of ' pear ' interpolated ' pineapple ' values ' (+ 1 2 3 4 5))
// 'a 1 string 2 with 42 lots 3 of 4 interpolated 5 values 15'


[examples]
(= prompt (fn (msg) (do (print msg) readl)))
(do
  (= name (prompt "what's your name? "))
  (printl (join 'Hello ' name '!')))



Chatgpt mentioned I probably want a way to quote a list in a `do` block. I think perhaps we can just have an express keyword which does this
```
(do
    (express (1 2 3 4 5 6))
)
```
apparently this is commonly accomplished with quoting?
```
(do '(1 2 3 4 5 6))
```
"""

# want tokenizing/parsing to be more combined
# also should be generators. i.e. tokenize()->Generator[Token], parse()->Generator[Expr]

def tokenize(): ...
