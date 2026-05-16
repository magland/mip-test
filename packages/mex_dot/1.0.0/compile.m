% Compile MEX for mex_dot
fprintf('Compiling mex_dot...\n');

src_dir = fileparts(mfilename('fullpath'));
original_dir = pwd;
cd(src_dir);

try
    mex('mex_dot.c');
    fprintf('MEX compilation OK\n');
catch ME
    cd(original_dir);
    rethrow(ME);
end

cd(original_dir);
