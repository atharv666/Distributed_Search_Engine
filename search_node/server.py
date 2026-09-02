import argparse, json, math, grpc
from collections import Counter, defaultdict
from concurrent import futures
from indexing.indexer.tokenizer import tokenize
from proto import search_pb2, search_pb2_grpc

class Service(search_pb2_grpc.SearchServiceServicer):
 def __init__(self,node_id,index,shard,stats):
  self.node_id=node_id;self.i=json.loads(open(index,encoding='utf8').read());self.s=json.loads(open(stats,encoding='utf8').read());self.docs={d['document_id']:d for d in map(json.loads,open(shard,encoding='utf8'))};self.norm=defaultdict(float)
  for term,e in self.i['terms'].items():
   for p in e['postings']: self.norm[p['document_id']]+=((p['term_frequency']/self.i['document_lengths'][str(p['document_id'])])*self.s['terms'][term]['idf'])**2
  self.norm={k:math.sqrt(v) for k,v in self.norm.items()}
 def Search(self,r,c):
  ts=tokenize(r.query,2,frozenset());q=Counter(ts);scores=defaultdict(float);qn=0
  for term,n in q.items():
   e=self.i['terms'].get(term);idf=self.s['terms'].get(term,{}).get('idf',0)
   if not e or not idf:continue
   w=n/len(ts)*idf;qn+=w*w
   for p in e['postings']: scores[p['document_id']]+=w*(p['term_frequency']/self.i['document_lengths'][str(p['document_id'])]*idf)
  out=[]
  for did,dot in scores.items():
   if self.norm[did]:
    d=self.docs[did];out.append(search_pb2.SearchResult(document_id=did,score=dot/(math.sqrt(qn)*self.norm[did]),title=d['title'],url=d['url'],snippet=d['content'][:240],node_id=self.node_id))
  return search_pb2.SearchResponse(results=sorted(out,key=lambda x:-x.score)[:r.top_k or 20],node_id=self.node_id,statistics_version=self.s['statistics_version'])
def main():
 p=argparse.ArgumentParser();[p.add_argument(x,required=True) for x in ('--node-id','--index','--shard','--statistics')];p.add_argument('--port',type=int,required=True);a=p.parse_args();s=grpc.server(futures.ThreadPoolExecutor(max_workers=4));search_pb2_grpc.add_SearchServiceServicer_to_server(Service(a.node_id,a.index,a.shard,a.statistics),s);s.add_insecure_port(f'[::]:{a.port}');s.start();print(f'{a.node_id} on {a.port}');s.wait_for_termination()
if __name__=='__main__':main()
