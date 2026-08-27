# Contributing to AI Security Mastery

Thanks for reading closely enough to want to improve this. Contributions that
make the book more correct, clearer, or more current are welcome.

## What's welcome

- **Corrections**: technical errors, broken code, wrong math, stale claims.
  These are the most valuable contributions a book can receive.
- **Clarity fixes**: a passage that confused you probably confuses others.
  Say where you got stuck and why.
- **Currency**: AI security moves fast. If an attack, defense, or reference
  in the book has been superseded, open an issue with a source.
- **Suggestions for v2.0**: especially in agentic/MCP security — see the
  Roadmap in the README.

## What's not a fit

- Large unsolicited content drops (whole new sections or chapters). Open an
  issue and discuss scope first — the book has one voice, and keeping it is
  deliberate.
- Bulk AI-generated pull requests. If a tool drafted it and you didn't verify
  every line, don't submit it.
- Style-only rewrites, reformatting, or "improvements" to prose that change
  no meaning.

## How to contribute

1. **Small fixes** (typos, a broken code line): open a pull request directly.
   One section per PR.
2. **Anything larger**: open an issue first. Describe the problem before
   proposing the solution.

## Ground rules for code in the book

- NumPy-first. Framework code only where the section is explicitly about a
  framework.
- Numerically stable: implementations must survive extreme inputs.
  Adversarial data is the whole point of this book.
- Verified: if you change a function that has a derivative, the numerical
  gradient check must still pass. If you add one, add its check.
- Every code block must run as-is when copied out of its YAML section, with
  only `requirements.txt` installed.

## Format conventions

- Book content lives in `book/`, one YAML file per section:
  `section_NN_MM_description.yaml`, indexed by `chapter_NN_index.yaml`.
- Match the structure of neighboring sections: `overview`,
  concept blocks, `security_implications`, `key_takeaways`.
- Every section connects to security. If a contribution doesn't answer
  "why does this matter for attack or defense," it isn't finished.

## License

By contributing, you agree your contributions are licensed under the MIT
License that covers the project.
