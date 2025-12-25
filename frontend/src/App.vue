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
            <div v-if="markdownContent" class="markdown-wrapper" ref="markdownWrapperRef">
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
import { ref, computed, nextTick, watch } from 'vue'
import { marked } from 'marked'
import FileUpload from './components/FileUpload.vue'

const markdownContent = ref('')
const markdownWrapperRef = ref(null)
const IMAGE_DOWNLOAD_API = './api/download-image'

const escapeHtml = (value = '') =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')

const renderer = new marked.Renderer()
// marked 4.x+ 版本中，image 方法接收 (href, title, text) 三个参数
renderer.image = (href = '', title = '', text = '') => {
  // 调试：记录所有参数
  console.log('图片渲染器被调用:', { 
    href, 
    title, 
    text,
    argsLength: arguments.length,
    allArgs: Array.from(arguments)
  })
  
  if (!href || href.trim() === '') {
    console.warn('图片URL为空或无效，跳过渲染', { href, title, text })
    // 如果 URL 为空，返回空字符串（不渲染），避免显示错误占位符
    return ''
  }

  console.log('处理图片:', { href, title, text })
  
  // 如果是 data URI，直接使用
  const isDataUri = href.startsWith('data:')
  
  let src
  if (isDataUri) {
    src = href
  } else if (href.startsWith('http://') || href.startsWith('https://')) {
    // 如果是完整的URL，检查是否是同源的 /static/ 路径
    try {
      const url = new URL(href)
      // 如果路径以 /static/ 开头，且是同源（开发环境可能需要代理，生产环境直接使用）
      if (url.pathname.startsWith('/static/')) {
        // 开发环境：使用代理路径；生产环境：直接使用（前后端同源）
        // 通过检查是否在开发环境来决定
        const isDev = import.meta.env.DEV
        if (isDev) {
          // 开发环境：通过 Vite 代理访问
          src = `/api${url.pathname}${url.search}`
          console.log(`开发环境：转换图片URL为代理路径: ${href} -> ${src}`)
        } else {
          // 生产环境：直接使用（前后端同源）
          src = url.pathname + url.search
          console.log(`生产环境：直接使用图片路径: ${href} -> ${src}`)
        }
      } else {
        // 其他外部URL，直接使用（可能需要CORS支持）
        src = href
      }
    } catch (e) {
      // URL解析失败，可能是相对路径，直接使用
      console.warn('URL解析失败，使用原始href:', href, e)
      src = href
    }
  } else if (href.startsWith('/static/')) {
    // 相对路径以 /static/ 开头
    const isDev = import.meta.env.DEV
    if (isDev) {
      // 开发环境：通过 Vite 代理访问
      src = `/api${href}`
      console.log(`开发环境：转换相对路径为代理路径: ${href} -> ${src}`)
    } else {
      // 生产环境：直接使用（前后端同源）
      src = href
      console.log(`生产环境：直接使用相对路径: ${href}`)
    }
  } else {
    // 其他相对路径或其他格式，通过代理下载
    src = `${IMAGE_DOWNLOAD_API}?image_url=${encodeURIComponent(href)}`
  }
  
  const titleAttr = title ? ` title="${escapeHtml(title)}"` : ''
  const altAttr = ` alt="${escapeHtml(text || '')}"`

  console.log('生成的图片src:', src)
  // 返回图片标签，事件监听会在 setupImageListeners 中添加
  return `<img src="${src}"${altAttr}${titleAttr} style="max-width: 100%; height: auto;" />`
}

// 配置 marked，确保正确处理图片和 HTML
marked.use({ 
  renderer,
  // 允许 HTML 标签（包括 img 标签）
  breaks: true,
  gfm: true
})

const renderedMarkdown = computed(() => {
  if (!markdownContent.value) return ''
  
  // 调试：检查 markdown 中的图片引用
  const imagePattern = /!\[([^\]]*)\]\(([^)]+)\)|<img[^>]+src=["']([^"']+)["']/gi
  const imageMatches = markdownContent.value.match(imagePattern)
  if (imageMatches) {
    console.log('Markdown中的图片引用:', imageMatches)
    imageMatches.forEach((match, index) => {
      const urlMatch = match.match(/\(([^)]+)\)|src=["']([^"']+)["']/i)
      if (urlMatch) {
        const url = urlMatch[1] || urlMatch[2]
        console.log(`  图片 ${index + 1}: URL = "${url}"`)
        if (!url || url.trim() === '') {
          console.error(`  警告: 图片 ${index + 1} 的URL为空!`, match)
        }
      } else {
        console.error(`  警告: 无法从图片引用中提取URL:`, match)
      }
    })
  }
  
  const html = marked.parse(markdownContent.value)
  // 等待DOM更新后设置图片监听器
  nextTick(() => {
    setupImageListeners()
  })
  return html
})

const handleMarkdownReady = (content) => {
  console.log('收到Markdown内容，长度:', content?.length)
  // 检查markdown中是否包含图片
  const imageMatches = content.match(/!\[([^\]]*)\]\(([^)]+)\)/g)
  if (imageMatches) {
    console.log('发现图片引用:', imageMatches)
    imageMatches.forEach(match => {
      const urlMatch = match.match(/\(([^)]+)\)/)
      if (urlMatch) {
        console.log('图片URL:', urlMatch[1])
      }
    })
  } else {
    console.warn('Markdown中没有找到图片引用')
  }
  markdownContent.value = content
  
  // 等待DOM更新后，为图片添加事件监听
  nextTick(() => {
    setupImageListeners()
  })
}

const setupImageListeners = () => {
  if (!markdownWrapperRef.value) return
  
  const images = markdownWrapperRef.value.querySelectorAll('img')
  console.log(`找到 ${images.length} 个图片元素`)
  
  images.forEach((img, index) => {
    console.log(`图片 ${index + 1}: src=${img.src}`)
    
    // 添加加载成功事件
    img.addEventListener('load', () => {
      console.log(`✅ 图片加载成功: ${img.src}`)
      img.style.border = 'none'
    })
    
    // 添加加载失败事件
    img.addEventListener('error', (e) => {
      console.error(`❌ 图片加载失败: ${img.src}`, e)
      img.style.border = '2px solid red'
      img.style.backgroundColor = '#ffebee'
      if (!img.alt.includes('加载失败')) {
        img.alt = `图片加载失败: ${img.src}`
      }
    })
    
    // 检查图片是否已经加载（可能缓存了）
    if (img.complete && img.naturalHeight !== 0) {
      console.log(`图片已缓存: ${img.src}`)
    }
  })
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

