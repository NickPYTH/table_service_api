import json

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ai_assistant.utils import call_ai_provider


@api_view(['POST'])
def process_prompt(request):
    query = request.data.get('query', '')
    context_str = request.data.get('context', '{}')
    conversation_id = request.data.get('conversationId')
    options = request.data.get('options', {})
    try:
        context = json.loads(context_str) if isinstance(context_str, str) else context_str
    except json.JSONDecodeError:
        context = {}

    if not query:
        return Response({
            'ok': False,
            'message': 'Пустой запрос.'
        }, status=status.HTTP_400_BAD_REQUEST)

    prompt_response = call_ai_provider(query, context, conversation_id, options)

    return Response({
        'ok': True,
        'data': prompt_response
    })
