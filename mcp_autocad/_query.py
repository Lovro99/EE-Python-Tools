import sys
sys.path.insert(0, '.')
from bridge import execute_lisp

# Broji svaki tip solarnog panela posebno i ukupno
result = execute_lisp(
    '(progn'
    ' (setq ss1 (ssget "X" (quote ((0 . "INSERT") (2 . "LONGI_SOLAR_415W"))))'
    '       ss2 (ssget "X" (quote ((0 . "INSERT") (2 . "LONGI_SOLAR_415W2"))))'
    '       cnt1 (if ss1 (sslength ss1) 0)'
    '       cnt2 (if ss2 (sslength ss2) 0))'
    ' (list cnt1 cnt2 (+ cnt1 cnt2))'
    ')'
)
print(result)
