# s3_actions
Processes a s3 action (post, delete) and pushes some data into datadog

# NB
This function increments a counter each time a s3 post action happens, this increments are currently
considered duplicates in our backend. We'd need either to update our backend, find a way to
aggregate api calls or use dogstatsd somewhere.
