# RAG and Chatbot Documentation

Documentation for Phase 4: Retrieval-Augmented Generation (RAG) chatbot with hybrid retrieval.

## Table of Contents

- [Phase 4 Overview](#phase-4-overview)
- [Hybrid Retriever Architecture](#hybrid-retriever-architecture)
- [Conversational Chain with Streaming](#conversational-chain-with-streaming)
- [Provider Switching in UI](#provider-switching-in-ui)
- [Token Tracking Display](#token-tracking-display)
- [Implementation Roadmap](#implementation-roadmap)

---

## Phase 4 Overview

Phase 4 implements a RAG-based chatbot for querying the knowledge graph and bug report corpus.

### Goals

1. **Hybrid Retrieval**: Combine BM25, vector embeddings, and graph traversal
2. **Conversational Interface**: Natural language queries with context
3. **Multi-Provider Support**: Runtime switching between Ollama, Claude, OpenAI, Gemini
4. **Token Tracking**: Monitor and display token usage in real-time
5. **Source Attribution**: Show which documents contributed to answers

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER QUERY                             │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                     QUERY ANALYSIS                               │
│  • Intent classification                                         │
│  • Entity extraction from query                                  │
│  • Query expansion                                               │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                   HYBRID RETRIEVAL (Parallel)                    │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   BM25      │  │   Vector     │  │    Graph     │          │
│  │  Keyword    │  │ Embeddings   │  │  Traversal   │          │
│  │   Search    │  │  (ChromaDB)  │  │   (Neo4j)    │          │
│  │   (25%)     │  │    (50%)     │  │    (25%)     │          │
│  └─────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                   RERANKING & FUSION                           │
│  • Reciprocal Rank Fusion (RRF)                                 │
│  • Diversity boosting                                            │
│  • Relevance scoring                                              │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│              CONTEXT ASSEMBLY & PROMPT BUILDING                  │
│  • Top-K documents selection                                     │
│  • Context window management                                     │
│  • Prompt template with sources                                  │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                   LLM GENERATION                                 │
│  • Multi-provider support                                        │
│  • Streaming responses                                           │
│  • Token usage tracking                                          │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                      RESPONSE                                     │
│  • Generated answer                                              │
│  • Source attribution                                            │
│  • Token usage stats                                             │
│  • Confidence score                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Hybrid Retriever Architecture

Combines three complementary retrieval methods for comprehensive results.

### Retrieval Methods

#### 1. BM25 Keyword Search (25% weight)

**Purpose:** Exact keyword matching for precise term retrieval.

**Implementation:**
```python
from rank_bm25 import BM25Okapi

class BM25Retriever:
    def __init__(self, documents: List[str]):
        self.tokenized_docs = [doc.split() for doc in documents]
        self.bm25 = BM25Okapi(self.tokenized_docs)
    
    def search(self, query: str, k: int = 10) -> List[Tuple[str, float]]:
        tokenized_query = query.split()
        scores = self.bm25.get_scores(tokenized_query)
        # Return top-k documents with scores
        return sorted(zip(documents, scores), 
                     key=lambda x: x[1], reverse=True)[:k]
```

**Best For:**
- Exact bug IDs (e.g., "Bug 123456")
- Technical terms
- Error messages
- File names

#### 2. Vector Embeddings (50% weight)

**Purpose:** Semantic similarity for conceptual matches.

**Implementation:**
```python
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

class VectorRetriever:
    def __init__(self, persist_directory: str):
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        self.vectorstore = Chroma(
            persist_directory=persist_directory,
            embedding_function=self.embeddings
        )
    
    def search(self, query: str, k: int = 10) -> List[Document]:
        return self.vectorstore.similarity_search(query, k=k)
    
    def add_documents(self, documents: List[Document]):
        self.vectorstore.add_documents(documents)
```

**Best For:**
- Conceptual similarity
- Paraphrased queries
- Related topics
- Semantic meaning

#### 3. Graph Traversal (25% weight)

**Purpose:** Relationship-based retrieval from knowledge graph.

**Implementation:**
```python
from src.kg import get_client

class GraphRetriever:
    def __init__(self):
        self.client = get_client()
        self.client.connect()
    
    def search(self, query: str, k: int = 10) -> List[Dict]:
        # Extract entities from query
        entities = self._extract_entities(query)
        
        # Query Neo4j for related nodes
        results = []
        for entity in entities:
            query = """
            MATCH (n)-[r]-(m)
            WHERE n.name CONTAINS $entity
            RETURN n, r, m, score
            LIMIT $k
            """
            results.extend(self.client.run_query(query, {
                "entity": entity,
                "k": k
            }))
        
        return results
    
    def _extract_entities(self, query: str) -> List[str]:
        # Use entity extraction chain
        from src.llm import extract_entities
        result = extract_entities(query)
        return [e.name for e in result.entities]
```

**Best For:**
- Related bugs
- Affected components
- Reporter history
- Component relationships

### Reciprocal Rank Fusion

Combines results from all three methods using RRF:

```python
def reciprocal_rank_fusion(
    results_dict: Dict[str, List[Tuple[str, float]]],
    weights: Dict[str, float] = None,
    k: int = 60
) -> List[Tuple[str, float]]:
    """
    Combine ranked lists using RRF.
    
    Formula: score = sum(weight_i / (k + rank_i))
    """
    if weights is None:
        weights = {'bm25': 0.25, 'vector': 0.50, 'graph': 0.25}
    
    fused_scores = {}
    
    for method, results in results_dict.items():
        weight = weights.get(method, 0.33)
        for rank, (doc_id, _) in enumerate(results):
            if doc_id not in fused_scores:
                fused_scores[doc_id] = 0
            fused_scores[doc_id] += weight / (k + rank)
    
    # Sort by fused score
    return sorted(fused_scores.items(), 
                  key=lambda x: x[1], reverse=True)
```

### Hybrid Retriever Class

```python
class HybridRetriever:
    def __init__(self):
        self.bm25 = BM25Retriever(documents)
        self.vector = VectorRetriever("chroma_db/")
        self.graph = GraphRetriever()
        self.weights = {
            'bm25': 0.25,
            'vector': 0.50,
            'graph': 0.25
        }
    
    def retrieve(self, query: str, k: int = 10) -> List[RetrievedDocument]:
        # Parallel retrieval
        bm25_results = self.bm25.search(query, k=k*2)
        vector_results = self.vector.search(query, k=k*2)
        graph_results = self.graph.search(query, k=k*2)
        
        # Fuse results
        all_results = {
            'bm25': bm25_results,
            'vector': [(d.metadata['id'], d) for d in vector_results],
            'graph': [(r['n']['id'], r) for r in graph_results]
        }
        
        fused = reciprocal_rank_fusion(all_results, self.weights)
        
        # Return top-k
        return [self._get_document(doc_id) 
                for doc_id, _ in fused[:k]]
```

---

## Conversational Chain with Streaming

### Architecture

```python
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate

class ConversationalRAGChain:
    def __init__(
        self,
        retriever: HybridRetriever,
        llm_client: UnifiedLLMClient,
        memory: Optional[ConversationBufferMemory] = None
    ):
        self.retriever = retriever
        self.llm = llm_client
        self.memory = memory or ConversationBufferMemory()
        
    def _build_prompt(
        self, 
        query: str, 
        context: List[RetrievedDocument]
    ) -> str:
        """Build prompt with context and sources."""
        
        context_text = "\n\n".join([
            f"[Source {i+1}] {doc.content}\n"
            f"From: {doc.metadata['source']}, "
            f"Page: {doc.metadata.get('page', 'N/A')}"
            for i, doc in enumerate(context)
        ])
        
        prompt = f"""You are a helpful assistant specializing in bug report analysis.
Answer the user's question based on the provided context from bug reports.

Context:
{context_text}

Chat History:
{self.memory.get_history()}

User Question: {query}

Instructions:
1. Answer based ONLY on the provided context
2. Cite sources using [Source X] notation
3. If the answer isn't in the context, say "I don't have enough information"
4. Be concise but thorough

Answer:"""
        
        return prompt
    
    def query(self, question: str) -> RAGResponse:
        """Non-streaming query."""
        # Retrieve context
        docs = self.retriever.retrieve(question, k=5)
        
        # Build prompt
        prompt = self._build_prompt(question, docs)
        
        # Generate response
        response = self.llm.chat_text(prompt)
        
        # Update memory
        self.memory.add_message(HumanMessage(content=question))
        self.memory.add_message(AIMessage(content=response.content))
        
        return RAGResponse(
            answer=response.content,
            sources=[doc.metadata for doc in docs],
            token_usage=response.token_usage,
            processing_time_ms=response.processing_time_ms
        )
    
    def stream_query(self, question: str) -> Generator[str, None, None]:
        """Streaming query with real-time token display."""
        # Retrieve context
        docs = self.retriever.retrieve(question, k=5)
        
        # Build prompt
        prompt = self._build_prompt(question, docs)
        
        # Stream response
        full_response = []
        for chunk in self.llm.stream_text(prompt):
            full_response.append(chunk)
            yield chunk
        
        # Update memory after completion
        complete_response = "".join(full_response)
        self.memory.add_message(HumanMessage(content=question))
        self.memory.add_message(AIMessage(content=complete_response))
```

### Streaming Implementation with Gradio

```python
import gradio as gr

class ChatbotUI:
    def __init__(self, chain: ConversationalRAGChain):
        self.chain = chain
        self.current_token_usage = TokenUsage()
    
    def create_interface(self):
        with gr.Blocks(title="Bug Report RAG Chatbot") as demo:
            gr.Markdown("# Bug Report Knowledge Graph Chatbot")
            
            # Chat interface
            chatbot = gr.Chatbot(height=500)
            msg = gr.Textbox(
                label="Ask a question about bug reports",
                placeholder="e.g., What bugs affect the JavaScript engine?"
            )
            
            # Controls
            with gr.Row():
                provider_dropdown = gr.Dropdown(
                    choices=self.chain.llm.get_available_providers(),
                    value=self.chain.llm.get_current_provider(),
                    label="LLM Provider"
                )
                stream_checkbox = gr.Checkbox(
                    label="Stream Response",
                    value=True
                )
            
            # Token tracking display
            with gr.Row():
                token_display = gr.JSON(
                    label="Token Usage",
                    value={"prompt": 0, "completion": 0, "total": 0}
                )
                status_display = gr.Textbox(
                    label="Status",
                    value="Ready",
                    interactive=False
                )
            
            # Event handlers
            msg.submit(
                self._handle_message,
                inputs=[msg, chatbot, provider_dropdown, stream_checkbox],
                outputs=[chatbot, msg, token_display, status_display]
            )
            
            provider_dropdown.change(
                self._switch_provider,
                inputs=[provider_dropdown],
                outputs=[status_display]
            )
        
        return demo
    
    def _handle_message(
        self,
        message: str,
        history: List[Tuple[str, str]],
        provider: str,
        stream: bool
    ):
        if not message:
            return history, "", self._get_token_json(), "Please enter a message"
        
        # Switch provider if needed
        if provider != self.chain.llm.get_current_provider():
            self.chain.llm.switch_provider(provider)
        
        # Add user message to history
        history.append([message, ""])
        
        if stream:
            # Streaming response
            response_chunks = []
            for chunk in self.chain.stream_query(message):
                response_chunks.append(chunk)
                history[-1][1] = "".join(response_chunks)
                # Update display (Gradio handles streaming updates)
                yield history, "", self._get_token_json(), "Generating..."
            
            final_response = "".join(response_chunks)
        else:
            # Non-streaming response
            response = self.chain.query(message)
            final_response = response.answer
            history[-1][1] = final_response
        
        # Get final token usage
        token_usage = self.chain.llm.get_last_token_usage()
        self.current_token_usage = token_usage
        
        yield history, "", self._get_token_json(), "Complete"
    
    def _switch_provider(self, provider: str):
        try:
            self.chain.llm.switch_provider(provider)
            return f"Switched to {provider}"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _get_token_json(self):
        return {
            "prompt": self.current_token_usage.prompt_tokens,
            "completion": self.current_token_usage.completion_tokens,
            "total": self.current_token_usage.total_tokens
        }

# Launch
if __name__ == "__main__":
    chain = ConversationalRAGChain(
        retriever=HybridRetriever(),
        llm_client=get_client()
    )
    
    ui = ChatbotUI(chain)
    demo = ui.create_interface()
    demo.launch(server_name="0.0.0.0", server_port=7860)
```

---

## Provider Switching in UI

### Supported Providers

| Provider | Model | Speed | Quality | Cost |
|----------|-------|-------|---------|------|
| Ollama | llama3.2:3b | Fast | Good | Free |
| Claude | claude-3-sonnet | Medium | Excellent | $$ |
| OpenAI | gpt-4-turbo | Medium | Excellent | $$$ |
| Gemini | gemini-pro | Fast | Good | $ |

### Implementation

```python
class ProviderManager:
    def __init__(self, llm_client: UnifiedLLMClient):
        self.llm = llm_client
        self.provider_stats = {}
    
    def get_available_providers(self) -> List[Dict]:
        """Get list of available providers with status."""
        providers = []
        
        for name in self.llm.get_available_providers():
            stats = self.provider_stats.get(name, {})
            providers.append({
                "name": name,
                "enabled": True,
                "current": name == self.llm.get_current_provider(),
                "avg_latency": stats.get("avg_latency", "N/A"),
                "total_tokens": stats.get("total_tokens", 0),
                "success_rate": stats.get("success_rate", 1.0)
            })
        
        return providers
    
    def switch_provider(self, provider_name: str) -> bool:
        """Switch to a different provider."""
        try:
            self.llm.switch_provider(provider_name)
            return True
        except Exception as e:
            logger.error(f"Failed to switch to {provider_name}: {e}")
            return False
    
    def update_stats(self, provider_name: str, latency: float, tokens: int):
        """Update provider statistics."""
        if provider_name not in self.provider_stats:
            self.provider_stats[provider_name] = {
                "calls": 0,
                "total_latency": 0,
                "total_tokens": 0,
                "errors": 0
            }
        
        stats = self.provider_stats[provider_name]
        stats["calls"] += 1
        stats["total_latency"] += latency
        stats["total_tokens"] += tokens
        stats["avg_latency"] = stats["total_latency"] / stats["calls"]
```

### Gradio UI Component

```python
# Provider selection with statistics
def create_provider_selector(manager: ProviderManager):
    providers = manager.get_available_providers()
    
    with gr.Row():
        provider_dropdown = gr.Dropdown(
            choices=[p["name"] for p in providers],
            value=next(p["name"] for p in providers if p["current"]),
            label="LLM Provider"
        )
        
        # Display provider stats
        stats_md = gr.Markdown(
            lambda p: f"""
            **Current Provider Stats:**
            - Avg Latency: {manager.provider_stats.get(p, {}).get('avg_latency', 'N/A')}ms
            - Total Tokens: {manager.provider_stats.get(p, {}).get('total_tokens', 0)}
            """
        )
    
    # Auto-update stats when provider changes
    provider_dropdown.change(
        lambda p: manager.switch_provider(p),
        inputs=[provider_dropdown],
        outputs=[status_display]
    )
    
    return provider_dropdown
```

---

## Token Tracking Display

### Real-Time Token Display

```python
class TokenTracker:
    def __init__(self):
        self.session_usage = TokenUsage()
        self.query_usage = TokenUsage()
        self.history = []
    
    def start_query(self):
        """Reset query-level tracking."""
        self.query_usage = TokenUsage()
    
    def add_tokens(self, prompt: int, completion: int):
        """Add tokens from a response."""
        self.query_usage.prompt_tokens += prompt
        self.query_usage.completion_tokens += completion
        self.query_usage.total_tokens += prompt + completion
        
        self.session_usage.prompt_tokens += prompt
        self.session_usage.completion_tokens += completion
        self.session_usage.total_tokens += prompt + completion
    
    def end_query(self, query_text: str):
        """Record completed query."""
        self.history.append({
            "query": query_text[:50] + "..." if len(query_text) > 50 else query_text,
            "tokens": self.query_usage.to_dict(),
            "timestamp": datetime.now().isoformat()
        })
    
    def get_display_data(self) -> Dict:
        """Get data for UI display."""
        return {
            "current_query": self.query_usage.to_dict(),
            "session_total": self.session_usage.to_dict(),
            "query_count": len(self.history),
            "avg_per_query": {
                "prompt": self.session_usage.prompt_tokens // max(len(self.history), 1),
                "completion": self.session_usage.completion_tokens // max(len(self.history), 1),
                "total": self.session_usage.total_tokens // max(len(self.history), 1)
            }
        }
```

### Gradio Display Component

```python
def create_token_display(tracker: TokenTracker):
    with gr.Column():
        gr.Markdown("### Token Usage")
        
        # Current query
        current_json = gr.JSON(
            label="Current Query",
            value={"prompt": 0, "completion": 0, "total": 0}
        )
        
        # Session total
        total_json = gr.JSON(
            label="Session Total",
            value={"prompt": 0, "completion": 0, "total": 0}
        )
        
        # Statistics
        stats_md = gr.Markdown(
            label="Statistics",
            value="Queries: 0 | Avg per query: 0 tokens"
        )
        
        # Cost estimate (for paid providers)
        cost_md = gr.Markdown(
            label="Estimated Cost",
            value="$0.00"
        )
    
    return current_json, total_json, stats_md, cost_md

# Update function
def update_token_display(tracker: TokenTracker, provider: str):
    data = tracker.get_display_data()
    
    current = data["current_query"]
    total = data["session_total"]
    avg = data["avg_per_query"]
    
    # Calculate cost based on provider
    cost = calculate_cost(provider, total["prompt"], total["completion"])
    
    return (
        current,
        total,
        f"Queries: {data['query_count']} | Avg per query: {avg['total']} tokens",
        f"${cost:.4f}"
    )

def calculate_cost(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate estimated cost based on provider pricing."""
    pricing = {
        "openai": {"prompt": 0.00001, "completion": 0.00003},  # per token
        "claude": {"prompt": 0.000003, "completion": 0.000015},
        "gemini": {"prompt": 0.0000005, "completion": 0.0000015},
        "ollama": {"prompt": 0, "completion": 0}  # Free
    }
    
    rates = pricing.get(provider, {"prompt": 0, "completion": 0})
    return (prompt_tokens * rates["prompt"] + 
            completion_tokens * rates["completion"])
```

---

## Implementation Roadmap

### Phase 4A: Core Infrastructure (Week 1-2)

#### Week 1: Vector Store Setup

- [ ] Install ChromaDB dependencies
  ```bash
  pip install chromadb langchain-chroma
  ```

- [ ] Create document embeddings pipeline
  ```python
  # scripts/create_embeddings.py
  from langchain_chroma import Chroma
  from langchain_huggingface import HuggingFaceEmbeddings
  
  def create_embeddings_from_results(results_dir: str):
      """Create vector embeddings from extraction results."""
      embeddings = HuggingFaceEmbeddings(
          model_name="sentence-transformers/all-MiniLM-L6-v2"
      )
      
      vectorstore = Chroma(
          persist_directory="chroma_db",
          embedding_function=embeddings
      )
      
      # Load and embed documents
      for result_file in Path(results_dir).glob("*_results.json"):
          docs = load_documents_from_result(result_file)
          vectorstore.add_documents(docs)
  ```

- [ ] BM25 index creation
  ```python
  # src/rag/bm25_retriever.py
  import pickle
  from rank_bm25 import BM25Okapi
  
  class BM25Index:
      def __init__(self, documents: List[str]):
          self.documents = documents
          self.tokenized = [doc.split() for doc in documents]
          self.index = BM25Okapi(self.tokenized)
      
      def save(self, path: str):
          with open(path, 'wb') as f:
              pickle.dump({
                  'documents': self.documents,
                  'index': self.index
              }, f)
      
      @classmethod
      def load(cls, path: str):
          with open(path, 'rb') as f:
              data = pickle.load(f)
          instance = cls.__new__(cls)
          instance.documents = data['documents']
          instance.index = data['index']
          return instance
  ```

#### Week 2: Hybrid Retriever Implementation

- [ ] Implement RRF fusion algorithm
- [ ] Create HybridRetriever class
- [ ] Graph traversal queries
- [ ] Integration tests

### Phase 4B: Conversational Chain (Week 3-4)

#### Week 3: Core RAG Chain

- [ ] Conversational memory management
  ```python
  from langchain.memory import ConversationBufferMemory
  
  class RAGMemory:
      def __init__(self, max_history: int = 10):
          self.memory = ConversationBufferMemory(
              return_messages=True,
              memory_key="chat_history"
          )
          self.max_history = max_history
  ```

- [ ] Prompt engineering
- [ ] Source attribution
- [ ] Context window management

#### Week 4: Streaming & UI

- [ ] Streaming response implementation
- [ ] Gradio interface design
- [ ] Real-time token display
- [ ] Source citation display

### Phase 4C: Advanced Features (Week 5-6)

#### Week 5: Provider Management

- [ ] Provider switching backend
- [ ] Provider statistics tracking
- [ ] Cost estimation
- [ ] Fallback mechanisms

#### Week 6: Optimization & Polish

- [ ] Query caching
- [ ] Result highlighting
- [ ] Export functionality
- [ ] Performance optimization

### Implementation Timeline

```
Week 1-2:  [████████████████████] Core Infrastructure
Week 3-4:  [████████████████████] Conversational Chain
Week 5-6:  [████████████████████] Advanced Features

Milestones:
  Week 2:  Hybrid retriever working end-to-end
  Week 4:  Basic chatbot functional
  Week 6:  Production-ready deployment
```

### File Structure

```
src/
├── rag/
│   ├── __init__.py
│   ├── retrievers/
│   │   ├── __init__.py
│   │   ├── bm25_retriever.py
│   │   ├── vector_retriever.py
│   │   ├── graph_retriever.py
│   │   └── hybrid_retriever.py
│   ├── chains/
│   │   ├── __init__.py
│   │   ├── conversational_rag.py
│   │   └── streaming_chain.py
│   ├── memory/
│   │   ├── __init__.py
│   │   └── rag_memory.py
│   └── utils/
│       ├── __init__.py
│       ├── fusion.py
│       └── token_tracker.py
└── web/
    ├── __init__.py
    ├── chatbot_ui.py
    └── components/
        ├── __init__.py
        ├── provider_selector.py
        ├── token_display.py
        └── source_citation.py

scripts/
├── create_embeddings.py
├── test_rag.py
└── launch_chatbot.py
```

### Testing Strategy

```python
# tests/rag/test_retrievers.py

def test_hybrid_retriever():
    """Test hybrid retrieval with known documents."""
    retriever = HybridRetriever(
        bm25_index=load_test_bm25(),
        vectorstore=load_test_chroma(),
        graph_client=mock_neo4j_client()
    )
    
    results = retriever.retrieve("Bug 123456 crash")
    
    assert len(results) > 0
    assert all(hasattr(r, 'content') for r in results)
    assert all(hasattr(r, 'metadata') for r in results)

def test_rrf_fusion():
    """Test Reciprocal Rank Fusion."""
    results = {
        'bm25': [('doc1', 0.9), ('doc2', 0.8)],
        'vector': [('doc2', 0.95), ('doc3', 0.85)],
        'graph': [('doc1', 0.7), ('doc3', 0.9)]
    }
    
    fused = reciprocal_rank_fusion(results)
    
    # doc1 should rank high (bm25 + graph)
    assert fused[0][0] == 'doc1'
    # All docs should be in results
    assert len(fused) == 3
```

---

## Summary

### Key Features

| Feature | Status | Description |
|---------|--------|-------------|
| BM25 Retrieval | Planned | Keyword-based search |
| Vector Retrieval | Planned | Semantic similarity |
| Graph Traversal | Planned | Neo4j relationship queries |
| Hybrid Fusion | Planned | RRF combining all methods |
| Streaming | Planned | Real-time response generation |
| Provider Switching | Planned | Runtime LLM provider change |
| Token Tracking | Planned | Live token usage display |
| Source Attribution | Planned | Cite sources in responses |

### Dependencies

```txt
# Additional requirements for Phase 4
rank-bm25>=0.2.2
chromadb>=0.4.0
langchain-chroma>=0.0.5
langchain-huggingface>=0.0.3
sentence-transformers>=2.2.0
gradio>=4.0.0
```

### Next Steps

1. Set up vector database (ChromaDB)
2. Create BM25 index from processed documents
3. Implement graph traversal queries
4. Build hybrid retriever with RRF
5. Develop conversational chain
6. Create Gradio UI
7. Add provider switching
8. Implement token tracking

---

**Status:** Planned (Phase 4)  
**Version:** 1.0  
**Last Updated:** March 18, 2026
