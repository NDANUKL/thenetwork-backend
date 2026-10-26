"""Type checks for the launch-supported legacy questionnaire inputs."""
from datetime import datetime
import math
import re


def answer_issue(kind, value, required=True, options=()):
    empty = value is None or isinstance(value,str) and not value.strip() or isinstance(value,list) and not value
    if empty:
        return 'A response is required.' if required else None
    if kind in ('text','short_text','long_text'):
        return None if isinstance(value,str) else 'Enter a text response.'
    if kind == 'number':
        try:
            if isinstance(value,bool) or not isinstance(value,(str,int,float)) or not math.isfinite(float(value)):
                return 'Enter a valid number.'
        except (ValueError,TypeError):
            return 'Enter a valid number.'
        return None
    if kind == 'date_time':
        try:
            if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?(?:Z|[+-]\d{2}:\d{2})',value) or datetime.fromisoformat(value.replace('Z','+00:00')).tzinfo is None:
                return 'Enter a valid date/time with its timezone.'
        except ValueError:
            return 'Enter a valid date/time with its timezone.'
        return None
    if kind in ('single_select','yes_no','rating_scale'):
        values=options or ('yes','no') if kind=='yes_no' else options
        return None if not values or str(value) in values else 'Choose an available answer.'
    if kind == 'multi_select':
        return None if isinstance(value,list) and all(isinstance(item,str) and item in options for item in value) else 'Choose only available answers.'
    if kind == 'gps_point':
        if not isinstance(value,dict):return 'Capture a valid location.'
        latitude,longitude=value.get('latitude'),value.get('longitude')
        valid=lambda n:isinstance(n,(int,float)) and not isinstance(n,bool) and math.isfinite(n)
        return None if valid(latitude) and valid(longitude) and abs(latitude)<=90 and abs(longitude)<=180 else 'Capture a valid location.'
    if kind in ('photo','file_attachment','signature'):
        if not isinstance(value,list) or any(not isinstance(item,dict) or not item.get('attachment_id') for item in value):return 'Attach the required evidence.'
        if kind=='signature' and any(item.get('kind')!='Signature' for item in value):return 'Use the signature pad for this question.'
        return None
    return 'This input type is not supported for launch.'
