FROM tmaier/docker-compose:latest

# Install bash
RUN apk add --no-cache --virtual .build-deps
RUN apk add bash

# Install aws-cli and python
RUN apk -Uuv add python py-pip
RUN pip install awscli

CMD ["/bin/bash"]
