#!/usr/bin/sh

# exit on first error
set -e

echo '==== test suite ======================================================';
python -c 'from werkzeug_dispatch.testsuite import main; main()';

echo '';
echo '==== pyflakes ========================================================';
pyflakes werkzeug_dispatch;

echo '';
echo '==== pep8 ============================================================';
pep8 werkzeug_dispatch;

echo '';
echo 'NO ERRORS DETETCTED';
