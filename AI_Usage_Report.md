AI Usage Report

# Gen AIs Used by various members 
> ChatGpt
> 
> Claude 

# Example Usage [For Coding]

... Inputs

- We will plan out the algorithm ourselves - Doing the main thinking. 
- Then we will give that plan when needed to an AI to fill in syntax. 
- This allows us to speed up the rate that we code at, while still understanding what an AI is coding and also ensures that we think for ourselves on how to code.

> \# Algorithm 1
> 
> def functionA():
> \# Inputs, Integer A, Variable B, Boolean C
> 
>&emsp;&emsp; \# Process   
> 
>&emsp;&emsp; \# Store (A * B) 
> 
>&emsp;&emsp; \# If that stored variable is greater than 100
> then  C becomes True, Otherwise C retains its previous value
>
>&emsp;&emsp; \# Outputs : C 

Algorithm 1 will then be sent to an LLM, which should output something like the following

> \# Algorithm 1
> 
> def functionA(IntA,IntB,BoolC):
>
> &emsp;&emsp; Ans = IntA * IntB
> 
> &emsp;&emsp; if Ans > 100:
> 
> &emsp;&emsp;&emsp;&emsp; BoolC = True 
> 
> &emsp;&emsp; return BoolC


