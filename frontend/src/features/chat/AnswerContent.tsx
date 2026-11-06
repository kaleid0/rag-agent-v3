import { memo } from 'react'
import Markdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import 'katex/dist/katex.min.css'

export default memo(function AnswerContent({ content }: { content: string }) {
  return (
    <div className="chat-markdown">
      <Markdown
        skipHtml
        disallowedElements={['img']}
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { trust: false }]]}
        components={{
          a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
          table: ({ node: _node, ...props }) => (
            <div className="chat-table-scroll" tabIndex={0} role="region" aria-label="回答中的表格">
              <table {...props} />
            </div>
          ),
        }}
      >
        {content}
      </Markdown>
    </div>
  )
})
