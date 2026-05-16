/*
 * mex_dot.c - dot product of two real double vectors.
 *
 * Usage: result = mex_dot(a, b)
 */
#include "mex.h"

void mexFunction(int nlhs, mxArray *plhs[],
                 int nrhs, const mxArray *prhs[])
{
    double *a, *b, sum;
    mwSize n, i;

    if (nrhs != 2)
        mexErrMsgIdAndTxt("mex_dot:nrhs", "Two inputs required.");
    if (nlhs > 1)
        mexErrMsgIdAndTxt("mex_dot:nlhs", "One output allowed.");
    if (!mxIsDouble(prhs[0]) || mxIsComplex(prhs[0]) ||
        !mxIsDouble(prhs[1]) || mxIsComplex(prhs[1]))
        mexErrMsgIdAndTxt("mex_dot:notDouble",
                          "Inputs must be real double arrays.");

    n = mxGetNumberOfElements(prhs[0]);
    if (mxGetNumberOfElements(prhs[1]) != n)
        mexErrMsgIdAndTxt("mex_dot:dimMismatch",
                          "Inputs must have the same number of elements.");

    a = mxGetPr(prhs[0]);
    b = mxGetPr(prhs[1]);

    sum = 0.0;
    for (i = 0; i < n; i++)
        sum += a[i] * b[i];

    plhs[0] = mxCreateDoubleScalar(sum);
}
