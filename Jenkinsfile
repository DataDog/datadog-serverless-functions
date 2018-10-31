#!groovy

@Library('ccp-jenkins-pipelines@master')
import ccp.jenkins.JqExpressionBuilder
import ccp.jenkins.Security

pipeline {

    agent { label 'ubuntu-docker-host' }

    options {
        timestamps()
        disableConcurrentBuilds()
        durabilityHint('PERFORMANCE_OPTIMIZED')
    }

    environment {
        aws_credential_env = 'aws-jenkins-poweruser'
        deployBucket = "spok-mgmt-deploy"
        region = "us-east-1"
    }

    stages {

        stage ('Build and Publish package'){
            when {
                not {
                    anyOf {
                        branch 'master'
                    }
                }
            }
            steps{

                script {
                    pr_number = env.CHANGE_ID ?: '0'
                }
                sh "zip dd-log-helper-${pr_number}.zip ${WORKSPACE}/Log/lambda_function.py"
                s3CpWithGrants("${WORKSPACE}/dd-log-helper-${pr_number}.zip", deployBucket, "datadog")

                echo "Package direct download link below (expires in 6 days):"

                withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', accessKeyVariable: 'AWS_ACCESS_KEY_ID', credentialsId: aws_credential_env, secretKeyVariable: 'AWS_SECRET_ACCESS_KEY'], string(credentialsId: 'datadogApiToken', variable: 'datadogApiToken')])
                {
                    // need to support s3v4 because s3 object encrypted with kms
                    sh "aws configure set default.s3.signature_version s3v4"

                    // generate presigned URL for easy download
                    sh "aws s3 presign --expires-in 518400 s3://${deployBucket}/datadog/dd-log-helper-${pr_number}.zip --region ${region} > package-presigned-url.txt"
                }   

                // output the url -- has to be done outside the credentials block otherwise the accesskeyid is masked
                sh "cat package-presigned-url.txt"
            }
        }


        stage('Promote to production'){
            when {
                branch 'master'
            }
            steps {

                script {
                    // get job name sans branch
                    prefixes = env.JOB_NAME.split('/')
                    job_name = prefixes[1]
                    job_path = prefixes[0] + '/' + prefixes[1]
                    // get the merged PR number by looking at git commit log
                    pr_number = sh returnStdout: true, script: "git log -1 | grep \'pull request\' | awk \'{print substr(\$4,2)}\'"
                    pr_number = pr_number.trim()
                    echo "The PR number merged was PR-${pr_number}."

                    // get the latest successful build from the merged PR
                    item = Jenkins.instance.getItemByFullName(job_path + '/PR-' + pr_number)
                    pr_build_number = item.getLastSuccessfulBuild().number.toString()
                    echo "The last successful PR-${pr_number} build was #${pr_build_number}"

                    s3GetObject(deployBucket, "datadog/dd-log-helper-${pr_number}.zip", "dd-log-helper-${pr_number}.zip")
                    sh "mv ${WORKSPACE}/dd-log-helper-${pr_number}.zip ${WORKSPACE}/dd-log-helper-latest.zip"
                    s3CpWithGrants("${WORKSPACE}/dd-log-helper-latest.zip", deployBucket, "datadog")
                }
            }
        }
    }
}