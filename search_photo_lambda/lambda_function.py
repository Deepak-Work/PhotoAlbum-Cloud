import boto3
import json
import os
from opensearchpy import OpenSearch, RequestsHttpConnection

lex = boto3.client('lexv2-runtime')

OPENSEARCH_HOST = os.environ['OPENSEARCH_HOST']
OPENSEARCH_USERNAME = os.environ['OPENSEARCH_USERNAME']
OPENSEARCH_PASSWORD = os.environ['OPENSEARCH_PASSWORD']

LEX_ALIAS_ID = os.environ['BOT_ALIAS_ID']
LEX_BOT_ID = os.environ['BOT_ID']
codepipeline = boto3.client('codepipeline')



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
    
    query = event['queryStringParameters']['q']
    
    # Disambiguate query using Lex
    lex_response = lex.recognize_text(
        botId = LEX_BOT_ID,
        botAliasId = LEX_ALIAS_ID,
        localeId='en_US',
        sessionId='test-session',
        text=query
    )
    
    # Extract keywords from Lex response
    keywords = []
    if 'interpretations' in lex_response:
        for interpretation in lex_response['interpretations']:
            if 'intent' in interpretation:
                for slot in interpretation['intent']['slots'].values():
                    if slot and 'value' in slot:
                        keywords.append(slot['value']['interpretedValue'])
    
    # If keywords found, search OpenSearch
    if keywords:
        search_query = {
            "query": {
                "multi_match": {
                    "query": " ".join(keywords),
                    "fields": ["labels"]
                }
            }
        }
        search_results = os_client.search(index="photos", body=search_query)
        return {
            'statusCode': 200,
            'body': json.dumps(search_results['hits']['hits'])
        }
    else:
        # Return empty array if no keywords found
        return {
            'statusCode': 200,
            'body': json.dumps([])
        }