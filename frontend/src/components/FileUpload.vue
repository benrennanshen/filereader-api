<template>
  <el-card class="upload-card" shadow="hover">
    <template #header>
      <div class="card-header">
        <el-icon class="header-icon"><document /></el-icon>
        <span>上传文件</span>
      </div>
    </template>
    <div class="upload-content">
      <el-upload
        class="upload-demo"
        drag
        :http-request="customUpload"
        :show-file-list="false"
        :disabled="loading"
      >
        <el-icon class="el-icon--upload" :size="64"><upload-filled /></el-icon>
        <div class="el-upload__text">
          将文件拖到此处，或<em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            <el-icon><info-filled /></el-icon>
            <span>支持格式：html / htm、txt、docx、xls / xlsx、pdf</span>
            <br>
            <span>文件大小限制：200MB</span>
          </div>
        </template>
      </el-upload>
      <div v-if="loading" class="loading-container">
        <el-progress
          :percentage="100"
          :indeterminate="true"
          :duration="3"
          status="success"
        />
        <div class="loading-text">
          <el-icon class="is-loading"><loading /></el-icon>
          <span>正在转换中，请稍候...</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Loading, Document, InfoFilled } from '@element-plus/icons-vue'
import axios from 'axios'

const emit = defineEmits(['markdown-ready'])

const loading = ref(false)

const customUpload = async (options) => {
  const file = options.file
  loading.value = true
  
  try {
    const formData = new FormData()
    formData.append('file', file)
    
    const response = await axios.post('/api/convert-to-md', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    
    loading.value = false
    
    if (response.data.httpCode === 200) {
      emit('markdown-ready', response.data.data)
      ElMessage.success('转换成功！')
    } else {
      ElMessage.error(response.data.message || '转换失败')
    }
  } catch (error) {
    loading.value = false
    let errorMessage = '上传失败'
    
    if (error.response) {
      const data = error.response.data
      if (data && data.message) {
        errorMessage = data.message
      } else {
        errorMessage = `请求失败: ${error.response.status}`
      }
    } else if (error.message) {
      errorMessage = error.message
    }
    
    ElMessage.error(errorMessage)
  }
}
</script>

<style scoped>
.upload-card {
  height: 100%;
  border-radius: 8px;
  transition: all 0.3s;
}

.upload-card :deep(.el-card__body) {
  padding: 24px;
  height: calc(100% - 57px);
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.header-icon {
  color: #409eff;
  font-size: 18px;
}

.upload-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.upload-demo {
  width: 100%;
}

.upload-demo :deep(.el-upload) {
  width: 100%;
}

.upload-demo :deep(.el-upload-dragger) {
  width: 100%;
  height: 280px;
  border: 2px dashed #d9d9d9;
  border-radius: 8px;
  background-color: #fafafa;
  transition: all 0.3s;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.upload-demo :deep(.el-upload-dragger:hover) {
  border-color: #409eff;
  background-color: #f0f9ff;
}

.el-icon--upload {
  color: #909399;
  margin-bottom: 16px;
  transition: all 0.3s;
}

.upload-demo :deep(.el-upload-dragger:hover) .el-icon--upload {
  color: #409eff;
  transform: scale(1.1);
}

.el-upload__text {
  color: #606266;
  font-size: 14px;
  text-align: center;
  margin-top: 8px;
}

.el-upload__text em {
  color: #409eff;
  font-style: normal;
  font-weight: 500;
  cursor: pointer;
}

.el-upload__tip {
  margin-top: 16px;
  text-align: center;
  color: #909399;
  font-size: 12px;
  line-height: 1.8;
}

.el-upload__tip .el-icon {
  margin-right: 4px;
  vertical-align: middle;
}

.loading-container {
  margin-top: 24px;
  padding: 20px;
  background-color: #f5f7fa;
  border-radius: 8px;
}

.loading-text {
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #409eff;
  font-size: 14px;
}

.loading-text .el-icon {
  font-size: 16px;
}
</style>

