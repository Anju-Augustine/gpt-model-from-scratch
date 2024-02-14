#Bigram Language Model with Transformer Architecture

##Overview:

This repository contains the implementation of a Bigram Language Model using a transformer-like architecture. The model is trained on Shakespeare's text and can generate text character by character.

##Key Features:

**Transformer Architecture:** The model comprises essential transformer components, including self-attention, feedforward layers, layer normalization, and positional embeddings.
**Training Loop:** Implements a training loop with periodic evaluation to monitor training and test loss.
**Model Generation:** A function is provided to generate text from the trained model.

##Hyperparameters

Adjust hyperparameters in bigram_llm.py to customize the training process.

##Input and Output Files

Input File: The training data is sourced from input data.txt, which contains Shakespeare's text.
Output File: The generated text can be found in output.txt after running the bigram_llm.py script.
