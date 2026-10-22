# Codeforces-pdf-problems

 This is a collection of solved and unsolved Codeforces problems. I generate these problems using the Python script `codeforces_pdf.py`.

To generate different sets of exercises, you should do something like the following:
```
mkdir -p ~/Projects/codeforces-pdf
cd ~/Projects/codeforces-pdf

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
