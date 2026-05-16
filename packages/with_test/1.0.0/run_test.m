% Test script for with_test
result = with_test();
assert(strcmp(result, 'with_test 1.0.0 from mip-test'), ...
    'with_test returned unexpected result: %s', result);
fprintf('SUCCESS\n');
