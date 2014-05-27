#!/usr/bin/sh

# exit on first error
set -e

echo '==== test suite ======================================================';
python -c 'from verktyg.testsuite import main; main()';

echo '';
echo '==== pyflakes ========================================================';
pyflakes verktyg;

echo '';
echo '==== pep8 ============================================================';
pep8 verktyg;

echo '';
echo 'NO ERRORS DETETCTED';
