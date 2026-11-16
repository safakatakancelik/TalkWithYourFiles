# Orchestration

| File | What it is |
|---|---|
| `machine.py` | The question's state machine: a pure function from state and event to the next state and commands |
| `engine.py` | Runs a question: executes the machine's commands (turns, rows, events) |
| `inputs.py` | Builds turn inputs from the database; `named()` finds files and agents named in a question |
| `validators.py` | The validation rules checked after every turn |
| `claims.py` | Claim rules, carried verdicts, the pass rule, and assembling the answer with citation markers |
| `arithmetic.py` | The safe arithmetic check of derived claims |
