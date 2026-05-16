% Test script for mex_dot
a = [1, 2, 3, 4];
b = [5, 6, 7, 8];
result = mex_dot(a, b);
expected = 1*5 + 2*6 + 3*7 + 4*8;
assert(result == expected, ...
    'mex_dot returned %g (expected %g)', result, expected);
fprintf('SUCCESS\n');
