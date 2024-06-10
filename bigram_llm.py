# Importing required libraries
import torch
import torch.nn as nn
from torch.nn import functional as F

# Hyperparameters
batchsize = 16 # Number of independent sequences to process in parallel
blocksize = 32 # Maximum context length for predictions
max_iters = 40000
eval_interval = 5000
learning_rate = 1e-3
device = 'cuda' if torch.cuda.is_available() else 'cpu'
eval_iters = 200
n_embd = 64 # Dimensionality of token embeddings
n_head = 4 # Number of heads for multihead attention
n_layer = 4
dropout = 0.0

torch.manual_seed(1337)

# Downloading dataset
!wget https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt

# Reading file into text variable
with open('input.txt', 'r', encoding = 'utf-8') as f:
  text = f.read()

# Finding the unique characters in the text
characters = sorted(list(set(text)))
vocab_size = len(characters) #vocabulary size

# Creating a mapping from characters to integers
s_to_i = { ch:i for i,ch in enumerate(characters)}
i_to_s = { i:ch for i,ch in enumerate(characters)}
encode = lambda s: [s_to_i[c] for c in s]
decode = lambda n : ''.join([i_to_s[i] for i in n])

# Encoding text and storing as a tensor
data = torch.tensor(encode(text), dtype=torch.long)

# Splitting train and test datasets in 90:10 ratio
n = int(0.9*len(data))
train = data[:n]
test = data[n:]

# Defining function to generate a small batch of inputs and targets
def get_batch(split):
    data = train if split== 'train' else test
    #generating random integers to choose from the batches
    ix = torch.randint(len(data)-blocksize, (batchsize,))
    x = torch.stack([data[i:i+blocksize] for i in ix])
    y = torch.stack([data[i+1:i+blocksize+1] for i in ix])
    x, y = x.to(device), y.to(device)
    return x,y

# Defining function to estimate loss for train and test datasets
@torch.no_grad()
def estimate_loss():
    out = {}
    model.eval()
    for split in ['train', 'test']:
        losses = torch.zeros(eval_iters)
        for k in range(eval_iters):
            X, Y = get_batch(split)
            logits, loss = model(X, Y)
            losses[k] = loss.item()
        out[split] = losses.mean()
    model.train()
    return out

## Self-Attention (keys, queries, values coming from same source x)

# One head of self-attention
class Head(nn.Module):

    def __init__(self, head_size):
        super().__init__()
        self.key = nn.Linear(n_embd, head_size, bias=False)
        self.query = nn.Linear(n_embd, head_size, bias=False)
        self.value = nn.Linear(n_embd, head_size, bias=False)
        self.register_buffer('tril', torch.tril(torch.ones(blocksize, blocksize)))

        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        B,T,C = x.shape
        k = self.key(x) # (B, T, C)
        q = self.query(x) # (B, T, C)
        # Computing attention scores (affinities)
        wei = q @ k.transpose(-2, -1) * C ** -0.5 # (B, T, 16) @ (B, 16, T) ---> (B, T, T)
        wei = wei.masked_fill(self.tril[:T, :T]==0, float('-inf')) # (B, T, T)
        wei = F.softmax(wei, dim=-1) # (B, T, T)
        wei = self.dropout(wei)
        # Performing weighted aggregation of the values
        v = self.value(x) # (B, T, C)
        out = wei @ v # (B, T, T) @ (B, T, C) ---> (B, T, C)
        return out

# Multihead self attention
class MultiHeadAttention(nn.Module):

    def __init__(self, num_heads, head_size):
        super().__init__()
        self.heads = nn.ModuleList([Head(head_size) for _ in range(num_heads)])
        self.proj = nn.Linear(n_embd, n_embd)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        out = torch.cat([h(x) for h in self.heads], dim=-1)
        out = self.dropout(self.proj(out))
        return out

# A simple linear layer followed by a non-linearity
class FeedFoward(nn.Module):

    def __init__(self, n_embd):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),
            nn.ReLU(),
            nn.Linear(4 * n_embd, n_embd),
            nn.Dropout(dropout),
        )

    def forward(self, x):
        return self.net(x)

# Transformer block: communication followed by computation
class Block(nn.Module):

    def __init__(self, n_embd, n_head):
        super().__init__()
        head_size = n_embd // n_head
        self.sa = MultiHeadAttention(n_head, head_size)
        self.ffwd = FeedFoward(n_embd)
        self.ln1 = nn.LayerNorm(n_embd)
        self.ln2 = nn.LayerNorm(n_embd)

    def forward(self, x):
        x = x + self.sa(self.ln1(x))
        x = x + self.ffwd(self.ln2(x))
        return x

## Bigram Language Model - simplest language model

# Defining model
class Bigram_Language_Model(nn.Module):

    def __init__(self):
        super().__init__()
        # Defining an embedding table - to map discrete tokens (such as words or indices) to continuous vectors.
        self.token_embedding_table = nn.Embedding(vocab_size, n_embd)
        # Defining position embedding for capturing sequence order
        self.position_embedding_table = nn.Embedding(blocksize, n_embd)
        # Transformer blocks for communication and computation
        self.blocks = nn.Sequential(*[Block(n_embd, n_head=n_head) for _ in range(n_layer)])
        # Final layer normalization
        self.ln_f = nn.LayerNorm(n_embd)
        # Defining a linear layer to get logits from token embeddings
        self.lm_head = nn.Linear(n_embd, vocab_size)

    def forward(self, idx, targets=None):
        B,T = idx.shape
        # Creating embedding table for the token - reads the logits for the next token
        # idx and targets are both (B,T) tensor of integers
        token_embd = self.token_embedding_table(idx) #B, T, C
        # Incorporating position information using position embedding
        position_embd = self.position_embedding_table(torch.arange(T)) # (T, C)
        x = token_embd + position_embd # (B, T, C)
        x = self.blocks(x) # (B, T, C)
        x = self.ln_f(x) # (B, T, C)
        logits = self.lm_head(x) # (B, T, C)

        # Calculating the cross entropy loss between input logits and target
        if targets is None:
          loss = None
        else:
          B, T, C = logits.shape
          logits = logits.view(B*T, C) # Cross entropy takes only 2D input, therefore converting the logits to 2D
          targets = targets.view(B*T)
          loss = F.cross_entropy(logits, targets)

        return logits, loss

    def generate(self, idx, max_new_tokens):
        for _ in range(max_new_tokens):
            # Cropping idx to the last blocksize tokens
            idx_cond = idx[:, -blocksize:]
            # Getting the predictions
            logits, loss = self(idx_cond)
            # Extracting the logits only from the last time step of each sequence in the batch
            logits = logits[:, -1, :] # becomes (B, C)
            # Applying softmax to get probabilities for each logits
            probs = F.softmax(logits, dim=-1) # (B, C). softmax applied along last dimension (C)
            # Generating sample from the distribution to get the next token based on probs
            idx_next = torch.multinomial(probs, num_samples=1) # (B, 1)
            # Appending sampled index to the running sequence
            idx = torch.cat((idx, idx_next), dim=1) # (B, T+1)
        return idx

model = Bigram_Language_Model()
m = model.to(device)
# Printing the number of parameters in the model
print(sum(p.numel() for p in m.parameters())/1e6, 'M parameters')

# Creating an PyTorch optimizer
optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)

for iter in range(max_iters):

    # Evaluating the loss on train and test datesets
    if iter % eval_interval == 0 or iter == max_iters - 1:
        losses = estimate_loss()
        print(f"step {iter}: train loss {losses['train']:.4f}, test loss {losses['test']:.4f}")

    # Sampling batch of data
    x_batch, y_batch = get_batch('train')

    # Computing and updating model parameters based on backpropagation
    logits, loss = model(x_batch, y_batch)
    optimizer.zero_grad(set_to_none=True) #resetting the gradients to 0
    loss.backward() # Computing gradients through backpropagation
    optimizer.step() # Updating model parameters based on computed gradients

# Generating from the model
context = torch.zeros((1, 1), dtype=torch.long, device = device)
print(decode(model.generate(context, max_new_tokens=2000)[0].tolist()))
