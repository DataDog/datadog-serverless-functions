ARG image
FROM $image

ARG dd_py_layer_zip
ARG dd_tracer_layer_zip

RUN echo $dd_py_layer_zip

# Install the layers (ADD with untar files)
ADD $dd_py_layer_zip /opt/
ADD $dd_tracer_layer_zip /opt/

# Copy the code into /var/task
COPY *.py /var/task/

ENV DD_API_KEY "fake-api-key"
ENV DD_SITE "datadog.com"
