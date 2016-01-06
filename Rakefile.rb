desc 'Initialize an function - use to create a new lambda function'
task :init, [:function] do |t, args|
  sh "cp -r sample #{args.function}"
  sh "cd #{args.function} && mkdir gen"
end

desc 'Build base - run to build base.zip from an initialized function'
task :'build-base' do
  sh "cd sample &&
      virtualenv env &&
      source env/bin/activate &&
      cd env/lib/python2.7/site-packages/ &&
      pip install datadog &&
      zip -r base * &&
      mv base.zip ../../../../../base.zip"
end

desc 'Update the function - builds the zip file, pushes to s3, and updates the lambda function'
task :push, [:function, :bucket] do |t, args|
  sh "cd #{args.function} &&
      mkdir -p gen &&
      cp ../base.zip gen/#{args.function}.zip &&
      zip -r -g gen/#{args.function}.zip main.py &&
      aws s3 cp gen/#{args.function}.zip s3://#{args.bucket}"
  sh "aws lambda update-function-code --function-name #{args.function} --s3-bucket #{args.bucket} --s3-key #{args.function}.zip"
end
