.PHONY: docker-build docker-run docker-stop docker-logs docker-clean

IMAGE_NAME = web-app
CONTAINER_NAME = web-app

# Build Docker image
docker-build:
	docker build -t $(IMAGE_NAME) .

# Run container
docker-run:
	docker run -d --name $(CONTAINER_NAME) -p 3000:3000 --env-file .env.local $(IMAGE_NAME)

# Stop container
docker-stop:
	docker stop $(CONTAINER_NAME)
	docker rm $(CONTAINER_NAME)

# View logs
docker-logs:
	docker logs -f $(CONTAINER_NAME)

# Clean up
docker-clean:
	docker stop $(CONTAINER_NAME) 2>/dev/null || true
	docker rm $(CONTAINER_NAME) 2>/dev/null || true
	docker rmi $(IMAGE_NAME) 2>/dev/null || true
