ARG image
FROM $image

ARG forwarder

# Add the code into /var/task (will unzip files)
ADD $forwarder /var/task/

CMD ["lambda_function.lambda_handler"]
