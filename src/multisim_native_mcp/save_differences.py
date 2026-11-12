"""Actionable differences between native saved document signatures."""
import json
from collections import Counter


def saved_differences(expected, actual, path='sheets'):
    if expected == actual:
        return []
    if isinstance(expected, dict) and isinstance(actual, dict):
        return [difference for key in sorted(expected.keys() | actual.keys())
                for difference in saved_differences(expected.get(key), actual.get(key), path+'.'+key)]
    if isinstance(expected, list) and isinstance(actual, list):
        if path.endswith(('.annotations', '.components', '.wires', '.wire_labels')):
            encode=lambda value:json.dumps(value, sort_keys=True, ensure_ascii=False)
            remaining=Counter(encode(value) for value in actual);differences=[]
            for value in expected:
                key=encode(value)
                if remaining[key]:remaining[key]-=1
                else:differences.append({'path':path,'kind':'missing','expected':value})
            for value in actual:
                key=encode(value)
                if remaining[key]:
                    differences.append({'path':path,'kind':'unexpected','actual':value});remaining[key]-=1
            return differences
        differences=[]
        for index in range(max(len(expected),len(actual))):
            differences.extend(saved_differences(expected[index] if index<len(expected) else None,
                                                actual[index] if index<len(actual) else None,
                                                path+'['+str(index)+']'))
        return differences
    return [{'path':path,'kind':'changed','expected':expected,'actual':actual}]


def difference_summary(differences):
    def describe(difference):
        value=difference.get('expected',difference.get('actual'))
        if isinstance(value,dict) and 'text' in value:
            position=value.get('transform',[])[4:6]
            return difference['path']+': '+difference['kind']+' '+repr(value['text'])+(' at '+str(tuple(position)) if position else '')
        return difference['path']+': '+difference['kind']+' '+json.dumps(value,ensure_ascii=False)
    return '; '.join(describe(d) for d in differences)
