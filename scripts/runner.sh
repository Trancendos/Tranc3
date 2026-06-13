# Deploy everything
chmod +x deploy-multi-cloud.sh
./deploy-multi-cloud.sh

# Or selective deployment
DEPLOY_EKS=false DEPLOY_AKS=false ./deploy-multi-cloud.sh  # GKE only
