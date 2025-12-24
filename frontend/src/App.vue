<template>
  <div class="app-container">
    <el-container class="main-container">
      <el-header class="app-header">
        <div class="header-content">
          <h1>文件转 Markdown</h1>
          <p class="header-desc">支持多种文档格式转换为 Markdown</p>
        </div>
      </el-header>
      <el-container class="content-container">
        <el-aside class="left-panel" width="400px">
          <FileUpload @markdown-ready="handleMarkdownReady" />
        </el-aside>
        <el-main class="right-panel">
          <el-card class="preview-card" shadow="never">
            <template #header>
              <div class="card-header">
                <span class="card-title">转换结果</span>
                <el-tag v-if="markdownContent" type="success" size="small">已转换</el-tag>
                <el-tag v-else type="info" size="small">等待上传</el-tag>
              </div>
            </template>
            <div v-if="markdownContent" class="markdown-wrapper">
              <div class="markdown-body" v-html="renderedMarkdown"></div>
            </div>
            <el-empty v-else description="请上传文件进行转换" :image-size="100" />
          </el-card>
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { marked } from 'marked'
import FileUpload from './components/FileUpload.vue'

const markdownContent = ref('')
const IMAGE_DOWNLOAD_API = '/api/download-image'

const escapeHtml = (value = '') =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')

const renderer = new marked.Renderer()
renderer.image = ({ href = '', title, text }) => {
  if (!href) return text || ''

  const isDataUri = href.startsWith('data:')
  const src = isDataUri ? href : `${IMAGE_DOWNLOAD_API}?image_url=${encodeURIComponent(href)}`
  const titleAttr = title ? ` title="${escapeHtml(title)}"` : ''
  const altAttr = ` alt="${escapeHtml(text || '')}"`

  return `<img src="${src}"${altAttr}${titleAttr} />`
}

marked.use({ renderer })

const renderedMarkdown = computed(() => {
  if (!markdownContent.value) return ''
  return marked.parse(markdownContent.value)
})

const handleMarkdownReady = (content) => {
  markdownContent.value = content
}
</script>

<style scoped>
.app-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
}

.main-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  padding: 0;
  height: 80px !important;
}

.header-content {
  padding: 0 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 100%;
}

.header-content h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  letter-spacing: 0.5px;
}

.header-desc {
  margin: 0;
  font-size: 14px;
  color: #909399;
  font-weight: normal;
}

.content-container {
  flex: 1;
  overflow: hidden;
}

.left-panel {
  background: #fff;
  border-right: 1px solid #e4e7ed;
  padding: 20px;
  overflow-y: auto;
  box-shadow: 2px 0 8px rgba(0, 0, 0, 0.05);
}

.right-panel {
  padding: 20px;
  background: #f5f7fa;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.preview-card {
  height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
}

.preview-card :deep(.el-card__body) {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 0;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.markdown-wrapper {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  background: #fff;
}

.markdown-body {
  max-width: 100%;
  line-height: 1.8;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
  line-height: 1.25;
}

.markdown-body :deep(h1) {
  font-size: 2em;
  border-bottom: 1px solid #eaecef;
  padding-bottom: 0.3em;
}

.markdown-body :deep(h2) {
  font-size: 1.5em;
  border-bottom: 1px solid #eaecef;
  padding-bottom: 0.3em;
}

.markdown-body :deep(p) {
  margin-bottom: 16px;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 16px;
}

.markdown-body :deep(table th),
.markdown-body :deep(table td) {
  border: 1px solid #dfe2e5;
  padding: 6px 13px;
}

.markdown-body :deep(table th) {
  background-color: #f6f8fa;
  font-weight: 600;
}

.markdown-body :deep(code) {
  background-color: rgba(27, 31, 35, 0.05);
  border-radius: 3px;
  font-size: 85%;
  margin: 0;
  padding: 0.2em 0.4em;
}

.markdown-body :deep(pre) {
  background-color: #f6f8fa;
  border-radius: 6px;
  font-size: 85%;
  line-height: 1.45;
  overflow: auto;
  padding: 16px;
  margin-bottom: 16px;
}

.markdown-body :deep(pre code) {
  background-color: transparent;
  border: 0;
  display: inline;
  margin: 0;
  padding: 0;
  font-size: 100%;
  word-break: normal;
  white-space: pre;
}

.markdown-body :deep(blockquote) {
  border-left: 4px solid #dfe2e5;
  padding: 0 1em;
  color: #6a737d;
  margin-bottom: 16px;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin-bottom: 16px;
  padding-left: 2em;
}

.markdown-body :deep(li) {
  margin-bottom: 0.25em;
}

.markdown-body :deep(img) {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
  margin: 16px 0;
}

.markdown-body :deep(hr) {
  height: 0.25em;
  padding: 0;
  margin: 24px 0;
  background-color: #e1e4e8;
  border: 0;
}
</style>

