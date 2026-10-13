# Use python:3.13-slim as a base image 
FROM python:3.13-slim

# Set /Day8 as a working directory
WORKDIR /CA_Caesarean/streamlit

# Copy environment.yml
COPY * ./

# Install required packages/libs
RUN pip install -r requirements.txt

# #xpose port 8501
EXPOSE 8501

# Run streamlit
# CMD ["streamlit", "run", "hw3.py", "--server.address", "0.0.0.0"]
# CMD streamlit run hw3.py --server.port=$PORT --server.address=0.0.0.0

CMD ["streamlit", "run", "dashboard.py", "--server.address", "0.0.0.0"]