import boto3
import logging
from botocore.exceptions import ClientError
import json
import base64
from opensearchpy import OpenSearch, RequestsHttpConnection
import os

# Instantiate logger
logger = logging.getLogger(__name__)

# connect to the Rekognition client
rekognition = boto3.client('rekognition')
codepipeline = boto3.client('codepipeline')


s3 = boto3.client('s3')
# es_endpoint = os.getenv('elasticsearch_endpoint')

# # Initialize Elasticsearch client
# es = Elasticsearch([{'host': es_endpoint, 'port': 443, 'use_ssl': True}])


# Set up OpenSearch client
OPENSEARCH_HOST = os.environ['OPENSEARCH_HOST']
OPENSEARCH_USERNAME = os.environ['OPENSEARCH_USERNAME']
OPENSEARCH_PASSWORD = os.environ['OPENSEARCH_PASSWORD']

os_client = OpenSearch(
    hosts=[OPENSEARCH_HOST],
    http_auth=(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD),  # Add your OpenSearch credentials if necessary
    use_ssl=True,
    verify_certs=True,
    connection_class=RequestsHttpConnection
)


def lambda_handler(event, context):

    if 'CodePipeline.job' in event:
        job_id = event['CodePipeline.job']['id']
        try:
            codepipeline.put_job_success_result(jobId=job_id)
        except Exception as e:
            codepipeline.put_job_failure_result(
                jobId=job_id,
                failureDetails={
                    'type': 'JobFailed',
                    'message': str(e)
                }
            )
        return {
            'statusCode': 200,
            'body': json.dumps('Processed as part of CodePipeline')
        }
    else:

        event = event['Records'][0]
        bucket = event['s3']['bucket']['name']
        key = event['s3']['object']['key']

        try:
            image = None
            s3_object = s3.head_object(Bucket = bucket, Key = key)
            custom_labels = s3_object.get('Metadata', {}).get('x-amz-meta-customlabels', '')
            
            A1 = [label.strip() for label in custom_labels.split(',')] if custom_labels else []

            image = s3.get_object(Bucket = bucket, Key = key)['Body'].read()

            response = rekognition.detect_labels(Image={'Bytes': image})

            labels = A1 + [label['Name'] for label in response['Labels']]

            es_document = {
                "objectKey": key,
                "bucket": bucket,
                "createdTimestamp": s3_object['LastModified'].isoformat(),
                "labels": labels
            }

            print("JSON object for ElasticSearch:")
            print(json.dumps(es_document, indent=2))
            statusCode = None

            try:
                os_client.index(index="photos", body=es_document)
                # es.index(index="photos", body=es_document)
            except Exception as e:
                print("ERROR IN INDEXING")
                print(e)
                statusCode = 500

            print(response)
            lambda_response = {
                "statusCode": statusCode if statusCode else 200,
                "body": json.dumps(response)
            }
            print("Labels found:")
            print(labels)

        except ClientError as client_err:

            error_message = "Couldn't analyze image: " + client_err.response['Error']['Message']

            lambda_response = {
                'statusCode': 400,
                'body': {
                    "Error": client_err.response['Error']['Code'],
                    "ErrorMessage": error_message
                }
            }
            logger.error("Error function %s: %s",
                            context.invoked_function_arn, error_message)


        except ValueError as val_error:
            lambda_response = {
                'statusCode': 400,
                'body': {
                    "Error": "ValueError",
                    "ErrorMessage": format(val_error)
                }
            }
            logger.error("Error function %s: %s",
                        context.invoked_function_arn, format(val_error))

    return lambda_response

