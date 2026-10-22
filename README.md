# Codeforces-and-CSES-pdf-problems

 This is a collection of solved and unsolved Codeforces and CSES problems. I generate these problems using the Python script `codeforces_pdf.py or cses_pdf.py`.

To generate different sets of exercises, you should do something like the following:
```
mkdir -p ~/Projects/codeforces-cses-pdf
cd ~/Projects/codeforces-cses-pdf

python3 -m venv .venv
source .venv/bin/activate

pip install requests beautifulsoup4 reportlab
```
Then:

Usage examples:
```
    python codeforces_pdf.py
    python codeforces_pdf.py --tag dp --min-rating 1500 --max-rating 1700 --limit 20
    python codeforces_pdf.py --tag graphs --tag dfs\\ and\\ similar --overwrite
```

```
    python cses_pdf.py --list                      # show all topics
    python cses_pdf.py "Dynamic Programming"       # all problems of a topic
    python cses_pdf.py graph                       # partial names work if unique
    python cses_pdf.py
```
